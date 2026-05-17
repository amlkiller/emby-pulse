from fastapi import APIRouter, Request
from app.routers.auth import is_admin_user  # 🔒 引入管理员权限检查
from fastapi.responses import StreamingResponse
import requests
import io
import json # 🔥 新增 json 模块用于解析
from app.core.config import cfg
# 🔥 引入核心适配器
from app.core.media_adapter import media_api

# 🔥 拼音首字母搜索支持
try:
    from pypinyin import pinyin, Style
    PINYIN_AVAILABLE = True
except ImportError:
    PINYIN_AVAILABLE = False

def get_pinyin_initials(text):
    """获取中文文本的拼音首字母，用于拼音穿透搜索"""
    if not PINYIN_AVAILABLE or not text:
        return ""
    try:
        result = []
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  # 是中文字符
                py_list = pinyin(char, style=Style.FIRST_LETTER)
                if py_list and py_list[0]:
                    result.append(py_list[0][0].upper())
            elif char.isalpha():  # 英文字母直接添加
                result.append(char.upper())
        return ''.join(result)
    except:
        return ""

def matches_pinyin_query(item_name, query):
    """检查查询是否匹配项目名称或其拼音首字母"""
    if not query:
        return True
    query_lower = query.lower()
    name_lower = item_name.lower()
    
    # 1. 直接匹配名称
    if query_lower in name_lower:
        return True
    
    # 2. 匹配拼音首字母
    initials = get_pinyin_initials(item_name)
    if initials and query_lower in initials.lower():
        return True
    
    # 3. 匹配全拼（每个字的拼音）
    if PINYIN_AVAILABLE:
        try:
            full_pinyin = ''.join([''.join([p[0] for p in pinyin(char, style=Style.NORMAL)]) for char in item_name if '\u4e00' <= char <= '\u9fff'])
            if full_pinyin and query_lower in full_pinyin.lower():
                return True
        except:
            pass
    
    return False

router = APIRouter()

# ==========================================
# 🌟 智能嗅探：版本与定制版检测
# ==========================================
_emby_sys_cache = None

def get_emby_sys_info():
    global _emby_sys_cache
    if _emby_sys_cache:
        return _emby_sys_cache
    try:
        # 🚀 替换为 media_api
        res = media_api.get("/System/Info/Public", timeout=3).json()
        _emby_sys_cache = {
            "Version": res.get("Version", "4.10.0.0"),
            "ServerName": res.get("ServerName", "")
        }
        return _emby_sys_cache
    except:
        return {"Version": "4.10.0.0", "ServerName": ""}

def is_new_emby_router(sys_info):
    if cfg.get("server_type") == "jellyfin":
        return True # Jellyfin 一律视为新路由
        
    server_name = sys_info.get("ServerName", "").lower()
    if "xiaoyu" in server_name or "小鱼" in server_name:
        return True
        
    version_str = sys_info.get("Version", "4.10.0.0")
    try:
        parts = version_str.split('.')
        major = int(parts[0])
        minor = int(parts[1])
        if major < 4 or (major == 4 and minor <= 7): return False
        return True
    except:
        return True

def get_emby_admin():
    try:
        # 🚀 替换为 media_api
        users = media_api.get("/Users", timeout=5).json()
        for u in users:
            if u.get("Policy", {}).get("IsAdministrator"): return u['Id']
        return users[0]['Id'] if users else None
    except:
        return None

@router.get("/api/library/image/{item_id}")
def proxy_emby_image(item_id: str, type: str = "Primary", width: int = 400):
    try:
        # 🚀 替换为 media_api (支持 stream)
        res = media_api.get(f"/Items/{item_id}/Images/{type}", params={"MaxWidth": width}, stream=True, timeout=5)
        if res.status_code == 200:
            headers = {
                "Cache-Control": "public, max-age=604800",
                "Access-Control-Allow-Origin": "*",
                "Content-Type": res.headers.get("content-type", "image/jpeg")
            }
            return StreamingResponse(io.BytesIO(res.content), headers=headers)
    except:
        pass
    return {"status": "error"}

def extract_media_badges(item):
    badges = []
    if "MediaSources" in item and item["MediaSources"]:
        source = item["MediaSources"][0]
        media_streams = source.get("MediaStreams", [])
        
        video_stream = next((s for s in media_streams if s["Type"] == "Video"), None)
        audio_stream = next((s for s in media_streams if s["Type"] == "Audio"), None)

        path_or_name = (source.get("Path", "") + " " + source.get("Name", "")).upper()
        if "REMUX" in path_or_name:
            badges.append({"type": "quality", "text": "REMUX", "color": "bg-blue-600 text-white border-blue-500"})

        if video_stream:
            width = video_stream.get("Width", 0)
            if width >= 3800:
                badges.append({"type": "res", "text": "4K", "color": "bg-gray-900 text-white border-gray-700 dark:bg-gray-100 dark:text-gray-900"})
            elif width >= 1900:
                badges.append({"type": "res", "text": "1080P", "color": "bg-blue-500 text-blue-100 border-blue-400"})
            
            video_range = video_stream.get("VideoRange", "").upper()
            video_range_type = video_stream.get("VideoRangeType", "").upper()
            
            if "DOVI" in video_range or "DOVI" in video_range_type:
                badges.append({"type": "fx", "text": "Dolby Vision", "color": "bg-gradient-to-r from-indigo-600 to-purple-600 text-white border-indigo-400"})
            if "HDR" in video_range or "HDR10" in video_range_type:
                badges.append({"type": "fx", "text": "HDR", "color": "bg-yellow-500 text-yellow-900 border-yellow-400"})
                
        if audio_stream:
            codec = audio_stream.get("Codec", "").upper()
            channels = audio_stream.get("Channels", 2)
            channel_str = "5.1" if channels == 6 else ("7.1" if channels == 8 else f"{channels}.0")
            badges.append({"type": "audio", "text": f"{codec} {channel_str}", "color": "bg-slate-700 text-slate-200 border-slate-600"})
    return badges

@router.get("/api/library/search")
def global_library_search(query: str, request: Request):
    if not request.session.get("user"): return {"status": "error", "message": "未登录"}

    # 🔥 核心修复：优先使用公网地址，没有公网时使用内网地址
    # 顺序：emby_public_url > emby_external_url > emby_public_host > emby_host（内网）
    raw_host = cfg.get("emby_public_url") or cfg.get("emby_external_url") or cfg.get("emby_public_host") or cfg.get("emby_host", "")
    
    # 🔥🔥🔥 处理 Pro 版配置中存在多个服务器或 JSON 列表的情况 🔥🔥🔥
    public_host = ""
    if isinstance(raw_host, str) and raw_host.strip().startswith("["):
        try:
            raw_host = json.loads(raw_host)
        except:
            pass

    if isinstance(raw_host, list) and len(raw_host) > 0:
        first = raw_host[0]
        public_host = first.get("url", "") if isinstance(first, dict) else str(first)
    elif isinstance(raw_host, dict):
        public_host = raw_host.get("url", "") or raw_host.get("host", "")
    else:
        public_host = str(raw_host)

    # 兜底：如果还是奇怪的字符，干脆留空使用内网地址
    if public_host.startswith("["):
        public_host = ""

    # 🔥 关键修复：确保始终有完整的 URL（包含协议和主机）
    public_host = public_host.rstrip('/')
    
    # 如果公网地址为空，强制使用 emby_host（内网地址）
    if not public_host:
        public_host = cfg.get("emby_host", "http://127.0.0.1:8096").rstrip('/')

    admin_id = get_emby_admin()
    if not admin_id: return {"status": "error", "message": "找不到管理员账号"}

    sys_info = get_emby_sys_info()
    use_new_route = is_new_emby_router(sys_info)

    try:
        # 🚀 替换为 media_api
        # 🔥 拼音搜索：扩大搜索范围，让前端过滤
        params = {
            "SearchTerm": query,
            "IncludeItemTypes": "Movie,Series",
            "Recursive": "true",
            "Fields": "Overview,MediaSources,ProviderIds,ImageTags,ProductionYear", 
            "Limit": 50  # 🔥 扩大范围，支持拼音过滤
        }
        res = media_api.get(f"/Users/{admin_id}/Items", params=params, timeout=10).json()
        items = res.get("Items", [])

        results = []
        for item in items:
            item_name = item.get("Name", "")
            
            # 🔥 拼音穿透搜索过滤：匹配原名、拼音首字母、全拼
            if not matches_pinyin_query(item_name, query):
                continue
            
            media_type = "movie" if item["Type"] == "Movie" else "tv"
            
            poster_url = ""
            if item.get("ImageTags", {}).get("Primary"): poster_url = f"/api/library/image/{item['Id']}?type=Primary&width=400"
            elif item.get("ImageTags", {}).get("Backdrop"): poster_url = f"/api/library/image/{item['Id']}?type=Backdrop&width=400"
            else:
                tmdb_id = item.get("ProviderIds", {}).get("Tmdb")
                if tmdb_id: poster_url = f"https://image.tmdb.org/t/p/w500/{tmdb_id}.jpg"
                else: poster_url = "/static/img/logo-dark.png" 

            if use_new_route: emby_url = f"{public_host}/web/index.html#!/item?id={item['Id']}&serverId={item.get('ServerId', '')}"
            else: emby_url = f"{public_host}/web/index.html#!/item/details.html?id={item['Id']}&serverId={item.get('ServerId', '')}"

            info = {
                "id": item["Id"], "name": item_name, "year": item.get("ProductionYear", "未知"),
                "overview": item.get("Overview", "暂无简介"), "type": media_type, "poster": poster_url,
                "emby_url": emby_url, "badges": [] 
            }

            if media_type == "movie":
                info["badges"].extend(extract_media_badges(item))
            elif media_type == "tv":
                try:
                    # 🚀 替换为 media_api
                    eps_res = media_api.get(f"/Shows/{item['Id']}/Episodes", params={"UserId": admin_id, "Fields": "ParentIndexNumber"}, timeout=5).json()
                    season_counts = {}
                    for ep in eps_res.get("Items", []):
                        s_idx = ep.get("ParentIndexNumber")
                        if s_idx and s_idx > 0: season_counts[s_idx] = season_counts.get(s_idx, 0) + 1
                    
                    for s_idx in sorted(season_counts.keys()):
                        info["badges"].append({"type": "season", "text": f"第{s_idx}季: {season_counts[s_idx]}集", "color": "bg-emerald-500 text-white border-emerald-400"})

                    first_ep_res = media_api.get(f"/Shows/{item['Id']}/Episodes", params={"UserId": admin_id, "Limit": 1, "Fields": "MediaSources"}, timeout=3).json()
                    if first_ep_res.get("Items"):
                        info["badges"].extend(extract_media_badges(first_ep_res["Items"][0]))
                except Exception: pass
            
            results.append(info)
            
            # 🔥 限制返回数量
            if len(results) >= 8:
                break

        return {"status": "success", "data": results}
    except Exception as e:
        return {"status": "error", "message": f"全局搜索请求失败: {str(e)}"}