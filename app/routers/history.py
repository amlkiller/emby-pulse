from fastapi import APIRouter, Request
from typing import Optional
from app.core.database import query_db, get_playback_column_name
from app.core.config import cfg
# 🔥 引入核心适配器
from app.core.media_adapter import media_api
# 🔥 引入共享 IP 归属地工具
from app.utils.ip_location import get_location, get_isp, get_location_with_isp
import math
import sqlite3
import os
import ipaddress
import time

router = APIRouter()

# ==================== 🔥 统计数据缓存 ====================
_history_stats_cache = {"data": None, "expires": 0}
HISTORY_STATS_CACHE_TTL = 300  # 5 分钟缓存

# ==================== 安全检查 ====================

def check_login(request: Request) -> bool:
    """检查用户是否登录（支持管理端和用户端）"""
    return request.session.get("user") is not None or request.session.get("req_user") is not None

# 🔥 检查是否为 IPv6 地址
def _is_ipv6(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).version == 6
    except:
        return False

# --- 内部工具：获取用户映射 ---
_user_map_cache = {"data": None, "expires": 0}
_valid_user_ids_cache = {"data": None, "expires": 0}
USER_CACHE_TTL = 300  # 5 分钟缓存

def get_user_map_local():
    # 🔥 使用缓存
    if _user_map_cache["data"] and time.time() < _user_map_cache["expires"]:
        return _user_map_cache["data"]
    
    user_map = {}
    try:
        res = media_api.get("/Users", timeout=2)
        if res.status_code == 200:
            for u in res.json():
                user_map[u['Id']] = u['Name']
            # 缓存结果
            _user_map_cache["data"] = user_map
            _user_map_cache["expires"] = time.time() + USER_CACHE_TTL
    except:
        pass
    return user_map

# --- 内部工具：获取有效用户ID列表（过滤已删除用户）---
def get_valid_user_ids():
    # 🔥 使用缓存
    if _valid_user_ids_cache["data"] and time.time() < _valid_user_ids_cache["expires"]:
        return _valid_user_ids_cache["data"]
    
    valid_ids = set()
    try:
        res = media_api.get("/Users", timeout=2)
        if res.status_code == 200:
            for u in res.json():
                valid_ids.add(u['Id'])
            # 缓存结果
            _valid_user_ids_cache["data"] = valid_ids
            _valid_user_ids_cache["expires"] = time.time() + USER_CACHE_TTL
    except:
        pass
    return valid_ids


@router.get("/api/history/list")
def api_get_history(
    request: Request,
    page: int = 1,
    limit: int = 20,
    user_id: Optional[str] = None,
    keyword: Optional[str] = None
):
    # 🔒 安全检查
    if not check_login(request):
        return {"status": "error", "message": "请先登录"}
    
    # 🔒 权限检查：普通用户只能查看自己的数据
    admin_user = request.session.get("user", {})
    req_user = request.session.get("req_user", {})
    is_admin = admin_user.get("auth_type") == "emby" or admin_user.get("role") == "admin"
    
    # 如果不是管理员，强制只能查看自己的数据
    if not is_admin:
        if req_user:
            # 用户社区用户，只能查看自己的数据
            user_id = req_user.get("Id")
        elif admin_user:
            # 非管理员的本地账号，只能查看自己的数据
            user_id = admin_user.get("id")
    
    try:
        where_clauses = []
        params = []

        hidden_users = cfg.get("hidden_users") or []
        if hidden_users:
            placeholders = ','.join(['?'] * len(hidden_users))
            where_clauses.append(f"UserId NOT IN ({placeholders})")
            params.extend(hidden_users)

        # 🔥 过滤已删除用户：只显示当前存在的用户数据
        valid_user_ids = get_valid_user_ids()
        if valid_user_ids:
            placeholders = ','.join(['?'] * len(valid_user_ids))
            where_clauses.append(f"UserId IN ({placeholders})")
            params.extend(list(valid_user_ids))

        if user_id and user_id != 'all':
            where_clauses.append("UserId = ?")
            params.append(user_id)

        if keyword:
            where_clauses.append("ItemName LIKE ?")
            params.append(f"%{keyword}%")

        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

        # 🔥 自动检测客户端列名，兼容不同版本数据库
        client_col = get_playback_column_name()
        
        # 🔥 动态检测可用列：直接查询表的第一行，看哪些列存在
        try:
            test_sql = "SELECT * FROM PlaybackActivity LIMIT 1"
            test_res = query_db(test_sql, [])
            if test_res and len(test_res) > 0:
                first_row = test_res[0]
                if hasattr(first_row, 'keys'):
                    available_columns = list(first_row.keys())
                elif isinstance(first_row, dict):
                    available_columns = list(first_row.keys())
                else:
                    available_columns = ["DateCreated", "UserId", "ItemId", "ItemName", "PlayDuration"]
            else:
                available_columns = ["DateCreated", "UserId", "ItemId", "ItemName", "PlayDuration"]
        except:
            available_columns = ["DateCreated", "UserId", "ItemId", "ItemName", "PlayDuration"]
        
        # 确保核心列存在，并按合理顺序排列
        core_columns = ["DateCreated", "UserId", "ItemId", "ItemName", "PlayDuration"]
        extra_columns = [col for col in available_columns if col not in core_columns]
        select_fields = core_columns + extra_columns

        # 🔥 优化：COUNT 查询使用索引，速度更快
        count_sql = f"SELECT COUNT(*) as c FROM PlaybackActivity{where_sql}"
        try:
            count_res = query_db(count_sql, params)
            total = count_res[0]['c'] if count_res else 0
        except:
            total = 0

        try:
            total_pages = math.ceil(total / limit) if limit > 0 else 1
        except:
            total_pages = 1

        # 🔥 优化：使用子查询优化大偏移量分页
        # 对于大偏移量，先获取 ID，再关联查询
        if page > 10:
            # 大偏移量优化：先获取 ID 列表
            id_sql = f"SELECT rowid FROM PlaybackActivity{where_sql} ORDER BY DateCreated DESC LIMIT ? OFFSET ?"
            id_rows = query_db(id_sql, params + [limit, (page - 1) * limit])
            if id_rows:
                rowids = [r['rowid'] for r in id_rows]
                rowid_placeholders = ','.join(['?' for _ in rowids])
                data_sql = f"SELECT {', '.join(select_fields)} FROM PlaybackActivity WHERE rowid IN ({rowid_placeholders}) ORDER BY DateCreated DESC"
                rows = query_db(data_sql, rowids)
            else:
                rows = []
        else:
            # 小偏移量直接查询
            offset = (page - 1) * limit
            data_sql = f"SELECT {', '.join(select_fields)} FROM PlaybackActivity{where_sql} ORDER BY DateCreated DESC LIMIT ? OFFSET ?"
            rows = query_db(data_sql, params + [limit, offset])

        # 🔥 优化：只查询当前页需要的 IP 数据，而不是全表
        local_ip_data = {}
        # 支持 Pro 版的配置目录（/workspace/config）
        if os.path.exists("/workspace"):
            data_dir = "/workspace/data"
        else:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        local_db_path = os.path.join(data_dir, "playback.db")

        if os.path.exists(local_db_path) and rows:
            try:
                # 🔥 优化：只查询当前页的 IP 数据
                item_ids = [r['ItemId'] for r in rows if r.get('ItemId')]
                user_ids = [r['UserId'] for r in rows if r.get('UserId')]
                
                local_conn = sqlite3.connect(local_db_path)
                local_conn.row_factory = sqlite3.Row
                local_c = local_conn.cursor()
                
                # 使用 IN 查询，只获取当前页的 IP 数据
                if item_ids and user_ids:
                    placeholders = ','.join(['?' for _ in item_ids])
                    user_placeholders = ','.join(['?' for _ in user_ids])
                    local_c.execute(f"""
                        SELECT UserId, ItemId, RemoteEndPoint, Location, ISP 
                        FROM PlaybackActivity 
                        WHERE ItemId IN ({placeholders}) AND UserId IN ({user_placeholders})
                        AND RemoteEndPoint IS NOT NULL AND RemoteEndPoint != ''
                    """, item_ids + user_ids)
                    for row in local_c.fetchall():
                        key = str(row['UserId']) + '_' + str(row['ItemId'])
                        if key not in local_ip_data:
                            local_ip_data[key] = {
                                'ip': row['RemoteEndPoint'] or '',
                                'location': row['Location'] or '',
                                'isp': row['ISP'] or ''
                            }
                local_conn.close()
            except Exception as e:
                print(f"[IP补充] 加载本地IP数据失败: {e}")

        user_map = get_user_map_local()
        result = []
        for row in rows:
            item = dict(row)
            item['UserName'] = user_map.get(item['UserId'], "未知用户")

            seconds = item.get('PlayDuration') or 0
            if seconds < 60:
                item['DurationStr'] = f"{seconds}秒"
            elif seconds < 3600:
                item['DurationStr'] = f"{round(seconds/60)}分钟"
            else:
                item['DurationStr'] = f"{round(seconds/3600, 1)}小时"

            try:
                item['DateStr'] = item['DateCreated'].replace('T', ' ')[:16]
            except:
                item['DateStr'] = item['DateCreated']

            # 🔥 优先使用本地数据库的 IP 信息（通过 UserId + ItemId 匹配）
            local_key = str(item.get('UserId', '')) + '_' + str(item.get('ItemId', ''))
            ip_found = False

            if local_key in local_ip_data and local_ip_data[local_key]['ip']:
                full_ip = local_ip_data[local_key]['ip']
                if len(full_ip) > 4:
                    item['IP'] = full_ip
                    # 🔥 直接使用本地数据库的归属地信息（包括 IPv6）
                    item['Location'] = local_ip_data[local_key]['location']
                    item['ISP'] = local_ip_data[local_key]['isp']
                    ip_found = True

            if not ip_found:
                # 🔥 优化：不再实时查询 Emby Sessions API，太慢
                # 只使用本地数据库中已有的 IP
                ip = row.get('RemoteEndPoint') or ''
                if ip:
                    # 智能去掉端口号
                    try:
                        ip_obj = ipaddress.ip_address(ip.split(',')[0].split(':')[0] if ',' in ip else ip.split(':')[0])
                        if ip_obj.version == 4 and ':' in ip and ip.count(':') == 1:
                            parts = ip.rsplit(':', 1)
                            if parts[-1].isdigit():
                                ip = parts[0]
                    except:
                        if ip.count(':') == 1 and ip.split(':')[-1].isdigit():
                            ip = ip.rsplit(':', 1)[0]
                item['IP'] = ip or ''

            # 组合归属地和运营商
            # 🔥 优化：不再实时查询IP归属地，只使用本地数据库的数据
            location = item.get('Location') or ''
            isp = item.get('ISP') or ''
            # 过滤无效占位符
            if location in ["", "未知地区", "未知"]:
                location = ""
            if isp in ["", "未知地区", "未知"]:
                isp = ""
            if location and isp:
                item['LocationStr'] = f"{location} · {isp}"
            elif location:
                item['LocationStr'] = location
            elif isp:
                item['LocationStr'] = isp
            else:
                item['LocationStr'] = '-'

            result.append(item)

        return {
            "status": "success",
            "data": result,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e), "data": []}


@router.get("/api/history/stats")
def api_get_history_stats(request: Request):
    # 🔒 安全检查
    if not check_login(request):
        return {"status": "error", "message": "请先登录"}
    
    # 🔥 尝试使用缓存
    if _history_stats_cache["data"] and time.time() < _history_stats_cache["expires"]:
        return _history_stats_cache["data"]
    
    """获取播放历史统计数据 - 从 playback_reporting.db 获取"""
    try:
        from datetime import datetime, timedelta

        # 获取今天日期范围
        now = datetime.now()
        today_start = now.strftime("%Y-%m-%d 00:00:00")
        today_end = now.strftime("%Y-%m-%d 23:59:59")

        # 隐藏用户
        hidden_users = cfg.get("hidden_users") or []

        # 🔥 获取有效用户ID（过滤已删除用户）
        valid_user_ids = get_valid_user_ids()

        # 构建过滤条件
        hidden_clause = ""
        valid_user_clause = ""
        params = []
        
        if hidden_users:
            placeholders = ','.join(['?'] * len(hidden_users))
            hidden_clause = f" AND UserId NOT IN ({placeholders})"
            params.extend(hidden_users)
        
        if valid_user_ids:
            placeholders = ','.join(['?'] * len(valid_user_ids))
            valid_user_clause = f" AND UserId IN ({placeholders})"
            params.extend(list(valid_user_ids))

        today_count = 0
        total_seconds = 0
        active_users = 0
        total_count = 0

        # 🔥 从 playback_reporting.db 获取统计数据（通过 query_db）
        # 今日播放次数
        try:
            sql = f"SELECT COUNT(*) as c FROM PlaybackActivity WHERE DateCreated >= ? AND DateCreated < ?{hidden_clause}{valid_user_clause}"
            res = query_db(sql, [today_start, today_end] + params)
            today_count = res[0]['c'] if res and res[0]['c'] else 0
        except Exception as e:
            print(f"[统计] 今日播放次数查询失败: {e}")

        # 今日播放总时长
        try:
            sql = f"SELECT SUM(PlayDuration) as total FROM PlaybackActivity WHERE DateCreated >= ? AND DateCreated < ?{hidden_clause}{valid_user_clause}"
            res = query_db(sql, [today_start, today_end] + params)
            total_seconds = res[0]['total'] if res and res[0]['total'] else 0
        except Exception as e:
            print(f"[统计] 今日播放时长查询失败: {e}")

        # 活跃用户数
        try:
            sql = f"SELECT COUNT(DISTINCT UserId) as c FROM PlaybackActivity WHERE DateCreated >= ? AND DateCreated < ?{hidden_clause}{valid_user_clause}"
            res = query_db(sql, [today_start, today_end] + params)
            active_users = res[0]['c'] if res and res[0]['c'] else 0
        except Exception as e:
            print(f"[统计] 活跃用户数查询失败: {e}")

        # 累计播放次数
        try:
            sql = f"SELECT COUNT(*) as c FROM PlaybackActivity WHERE 1=1{hidden_clause}{valid_user_clause}"
            res = query_db(sql, params)
            total_count = res[0]['c'] if res and res[0]['c'] else 0
        except Exception as e:
            print(f"[统计] 累计播放次数查询失败: {e}")

        # 格式化时长
        if total_seconds < 60:
            today_duration = f"{int(total_seconds)}秒"
        elif total_seconds < 3600:
            today_duration = f"{int(total_seconds/60)}分钟"
        else:
            today_duration = f"{round(total_seconds/3600, 1)}小时"

        result = {
            "status": "success",
            "data": {
                "today_count": today_count,
                "today_duration": today_duration,
                "active_users": active_users,
                "total_count": total_count
            }
        }
        # 🔥 缓存结果
        _history_stats_cache["data"] = result
        _history_stats_cache["expires"] = time.time() + HISTORY_STATS_CACHE_TTL
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}