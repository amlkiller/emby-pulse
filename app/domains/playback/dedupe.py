import logging
import re
import threading
import time
from collections import defaultdict
from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.infra.clients.media_server_client import media_api
from app.infra.config.media_server_settings import get_media_server_main_public_or_host
from app.domains.playback.dedupe_dao import (
    DedupeResultWriter,
    add_dedupe_whitelist_items,
    delete_dedupe_result_by_item_id,
    get_dedupe_config_values,
    init_dedupe_tables,
    list_dedupe_results,
    list_dedupe_whitelist,
    list_dedupe_whitelist_group_keys,
    remove_dedupe_whitelist_items,
    save_dedupe_config_values,
)
from app.domains.users import public_service as user_service
from app.core.security_utils import safe_error_message

logger = logging.getLogger("uvicorn")
router = APIRouter(prefix="/api/dedupe", tags=["去重管理"])

scan_state = {
    "is_scanning": False,
    "progress": 0,
    "total_items": 0,
    "duplicate_groups": 0,
    "message": "空闲中"
}

def init_dedupe_db():
    try:
        init_dedupe_tables(logger)
        logger.info("[去重引擎] 数据库表初始化完成")
    except Exception as e:
        logger.error(f"[去重引擎] 自动建表失败: {e}")


def calculate_score(src: dict, strategy: str = "quality", custom_weights: dict = None):
    score = 0
    video = next((s for s in src.get("MediaStreams", []) if s.get("Type") == "Video"), {})
    audio = next((s for s in src.get("MediaStreams", []) if s.get("Type") == "Audio"), {})
    subs = [s for s in src.get("MediaStreams", []) if s.get("Type") == "Subtitle"]
    
    w = {"res": 40, "bitrate": 20, "codec": 5, "hdr": 15, "chi": 10, "ass": 15}
    if strategy == "subs": w = {"res": 15, "bitrate": 10, "codec": 5, "hdr": 10, "chi": 40, "ass": 30}
    elif strategy == "size": w = {"res": 20, "bitrate": 10, "codec": 30, "hdr": 10, "chi": 10, "ass": 10}
    elif strategy == "custom" and custom_weights: w = custom_weights

    width = video.get("Width") or 0
    res_str = "未知"
    if width >= 3800: score += w.get("res", 40); res_str = "4K"
    elif width >= 1900: score += w.get("res", 40) // 2; res_str = "1080P"
    elif width >= 1200: score += w.get("res", 40) // 4; res_str = "720P"
    elif width > 0: res_str = f"{width}P"
    
    bitrate = src.get("Bitrate") or 0
    if bitrate > 0: score += min(w.get("bitrate", 20), int((bitrate / 1000000) / 2))
        
    codec = video.get("Codec", "").lower()
    if "hevc" in codec or "x265" in codec or "av1" in codec: score += w.get("codec", 5)
        
    v_range = video.get("VideoRange", "")
    v_title = video.get("DisplayTitle", "").upper()
    if "DOVI" in v_title or "DOLBY VISION" in v_title: score += w.get("hdr", 15)
    elif "HDR" in v_range or "HDR" in v_title: score += int(w.get("hdr", 15) * 0.6)
    
    a_codec = audio.get("Codec", "").lower()
    has_chi = has_ass = False
    for sub in subs:
        lang = sub.get("Language", "").lower()
        if lang in ["chi", "zho", "chs", "cht", "zh"]:
            has_chi = True
            sub_codec = sub.get("Codec", "").lower()
            if "ass" in sub_codec or "ssa" in sub_codec: has_ass = True
            
    if has_chi: score += w.get("chi", 10)
    if has_ass: score += w.get("ass", 15)
        
    size = src.get("Size") or 0
    if strategy == "size" and size > 0: score -= int((size / (1024**3)) * 2)
        
    return score, {
        "res": res_str,
        "has_hdr": 1 if ("HDR" in v_range or "HDR" in v_title) else 0,
        "has_dovi": 1 if ("DOVI" in v_title or "DOLBY VISION" in v_title) else 0,
        "has_chi": 1 if has_chi else 0,
        "has_ass": 1 if has_ass else 0,
        "v_codec": codec.upper() if codec else "未知编码",
        "a_codec": a_codec.upper() if a_codec else "未知音轨"
    }

def run_dedupe_scan(strategy: str = "quality", custom_weights: dict = None, excluded_libraries: list = None):
    global scan_state
    start_time = time.time()
    logger.info(f"🚀 [去重引擎] 开始全库扫描，策略: {strategy}...")
    logger.info(f"[去重引擎] 屏蔽的媒体库: {excluded_libraries}")

    scan_state["is_scanning"] = True
    scan_state["progress"] = 0
    scan_state["message"] = "阶段一：构建剧集映射树..."

    excluded_libs = set(excluded_libraries or [])
    try:
        admin_res = media_api.get("/Users", timeout=5).json()
        admin_id = next((u['Id'] for u in admin_res if u.get("Policy", {}).get("IsAdministrator")), admin_res[0]['Id'])

        # 获取所有媒体库（使用 /Library/VirtualFolders API 更可靠）
        all_libraries = []
        try:
            lib_res = media_api.get("/Library/VirtualFolders", timeout=10)
            if lib_res.status_code == 200:
                all_libraries = lib_res.json()
        except Exception as e:
            logger.warning(f"[去重引擎] 获取媒体库失败: {e}")

        # 过滤掉屏蔽的媒体库
        active_libraries = [lib for lib in all_libraries if (lib.get("Guid") or lib.get("Id")) not in excluded_libs and lib.get("Name") not in excluded_libs]
        logger.info(f"[去重引擎] 媒体库总数: {len(all_libraries)}, 有效媒体库: {len(active_libraries)}")
        logger.info(f"[去重引擎] 所有媒体库: {[lib.get('Name') for lib in all_libraries]}")
        logger.info(f"[去重引擎] 有效媒体库: {[lib.get('Name') for lib in active_libraries]}")

        series_map = {}
        # 从每个有效媒体库获取 Series
        for lib in active_libraries:
            lib_id = lib.get("Guid") or lib.get("Id")
            try:
                s_res = media_api.get(f"/Users/{admin_id}/Items", params={
                    "ParentId": lib_id,
                    "IncludeItemTypes": "Series",
                    "Recursive": "true",
                    "Fields": "ProviderIds",
                }, timeout=15).json().get("Items", [])
                for s in s_res:
                    tmdb_id = s.get("ProviderIds", {}).get("Tmdb")
                    if tmdb_id: series_map[s["Id"]] = tmdb_id
            except Exception as e:
                logger.warning(f"[去重引擎] 从媒体库 {lib.get('Name')} 获取Series失败: {e}")

        scan_state["message"] = "阶段二：极速抽取全库索引..."
        items = []
        # 从每个有效媒体库获取 Movie 和 Episode
        for lib in active_libraries:
            lib_id = lib.get("Guid") or lib.get("Id")
            start = 0; limit = 10000
            lib_items = []
            while True:
                chunk = media_api.get(f"/Users/{admin_id}/Items", params={
                    "ParentId": lib_id,
                    "IncludeItemTypes": "Movie,Episode",
                    "Recursive": "true",
                    "Fields": "ProviderIds,ParentIndexNumber,IndexNumber,IndexNumberEnd,SeriesId,MediaSources",
                    "StartIndex": start,
                    "Limit": limit,
                }, timeout=30).json().get("Items", [])
                lib_items.extend(chunk)
                if len(chunk) < limit: break
                start += limit
            items.extend(lib_items)
            scan_state["message"] = f"阶段二：已抽取 {len(items)} 条索引..."
            
        scan_state["total_items"] = len(items)
        scan_state["message"] = "阶段三：内存哈希碰撞匹配中..."
        
        whitelist = list_dedupe_whitelist_group_keys()
        groups = defaultdict(list)
        skipped_no_tmdb = 0
        for i in items:
            mtype = i.get("Type")
            if mtype == "Movie":
                tmdb = i.get("ProviderIds", {}).get("Tmdb")
                imdb = i.get("ProviderIds", {}).get("Imdb")
                # 如果没有TMDB，尝试用IMDB，否则用Item ID
                if tmdb:
                    g_key = f"movie_tmdb_{tmdb}"
                elif imdb:
                    g_key = f"movie_imdb_{imdb}"
                else:
                    # 没有TMDB/IMDB的电影，用名称+年份作为分组键
                    name = i.get("Name", "").strip().lower()
                    year = i.get("ProductionYear", 0)
                    if name:
                        g_key = f"movie_name_{name}_{year}"
                    else:
                        skipped_no_tmdb += 1
                        continue
            elif mtype == "Episode":
                series_id = i.get("SeriesId") or i.get("ParentId") or "unknown"
                series_tmdb = series_map.get(series_id)
                if series_tmdb:
                    g_key = f"tv_{series_tmdb}_s{i.get('ParentIndexNumber', 0)}e{i.get('IndexNumber', 0)}"
                else:
                    # 如果没有TMDB，用Series名称+季集
                    series_name = i.get("SeriesName", "").strip().lower()
                    if series_name:
                        g_key = f"tv_name_{series_name}_s{i.get('ParentIndexNumber', 0)}e{i.get('IndexNumber', 0)}"
                    else:
                        g_key = f"tv_id_{series_id}_s{i.get('ParentIndexNumber', 0)}e{i.get('IndexNumber', 0)}"
            else: continue

            if g_key not in whitelist: groups[g_key].append(i)

        if skipped_no_tmdb > 0:
            logger.warning(f"[去重引擎] 跳过 {skipped_no_tmdb} 个没有TMDB/IMDB/名称的电影")

        # 🔥 修复关键：不再单纯依靠 Item 的数量判断，而是计算其内部包含的 MediaSource 物理文件总数！
        dup_groups = {}
        for k, v in groups.items():
            total_sources = sum([len(item.get("MediaSources", [{}])) for item in v])
            # 调试日志：显示每个分组的情况
            if len(v) > 1 or total_sources > 1:
                logger.info(f"[去重引擎] 分组检查: {k}, {len(v)} 个Item, {total_sources} 个MediaSource")
                for item in v:
                    logger.info(f"[去重引擎]   - Item: {item.get('Name')}, ID: {item.get('Id')}, MediaSources: {len(item.get('MediaSources', []))}")
            if total_sources > 1:
                dup_groups[k] = v
                logger.info(f"[去重引擎] 发现重复组: {k}, {len(v)} 个Item, {total_sources} 个MediaSource")

        # 🔥 新增：按文件夹路径检测同一文件夹内的重复文件（不同Item但同目录）
        # 只针对电影，剧集已在上面按 TMDB+季集 分组
        folder_groups = defaultdict(list)
        for i in items:
            # 只处理电影类型
            if i.get("Type") != "Movie":
                continue
                
            # 注意：不跳过有 TMDB/IMDB 的电影，因为可能存在同一文件夹内不同版本
                
            # 获取文件路径（从MediaSources中提取）
            media_sources = i.get("MediaSources", [])
            for src in media_sources:
                file_path = src.get("Path", "")
                if file_path:
                    # 提取文件夹路径（去掉文件名）
                    folder_path = "/".join(file_path.replace("\\", "/").split("/")[:-1])
                    if folder_path:
                        # 按文件夹+名称相似度分组
                        name_key = i.get("Name", "").strip().lower()
                        year = i.get("ProductionYear", 0)
                        # 移除常见的质量标记来匹配相似名称（包括DV P5这类带空格的）
                        base_name = re.sub(r'\s*[-._]?\s*(1080p|720p|4k|2160p|hdr|dv\s*p\d*|dv|x264|x265|hevc|av1|blu.?ray|web.?dl|bdrip|webrip|h\.?265|h\.?264|ddp|atmos|5\.1|7\.1).*', '', name_key, flags=re.IGNORECASE)
                        folder_key = f"folder_{folder_path}_{base_name}_{year}"
                        if folder_key not in whitelist:
                            folder_groups[folder_key].append(i)
                        break  # 只取第一个MediaSource的路径

        # 将同文件夹的重复文件加入重复组
        folder_dup_count = 0
        for folder_key, folder_items in folder_groups.items():
            total_sources = sum([len(item.get("MediaSources", [{}])) for item in folder_items])
            if total_sources > 1 and folder_key not in dup_groups:
                dup_groups[folder_key] = folder_items
                folder_dup_count += 1
                logger.info(f"[去重引擎] 发现同文件夹重复组: {folder_key}, {len(folder_items)} 个Item, {total_sources} 个MediaSource")

        if folder_dup_count > 0:
            logger.info(f"[去重引擎] 通过文件夹路径额外发现 {folder_dup_count} 个重复组")

        # 记录分组统计
        logger.info(f"[去重引擎] 总项目数: {len(items)}, 分组数: {len(groups)}, 重复组: {len(dup_groups)}")

        scan_state["duplicate_groups"] = len(dup_groups)
        
        total_dups = len(dup_groups); current = 0
        with DedupeResultWriter() as result_writer:
            for g_key, item_list in dup_groups.items():
                current += 1
                scan_state["progress"] = int((current / total_dups) * 100)
                scan_state["message"] = f"阶段四：深层分析视频流 ({current}/{total_dups})"
                
                ids = ",".join([i["Id"] for i in item_list])
                details = media_api.get(f"/Users/{admin_id}/Items", params={
                    "Ids": ids,
                    "Fields": "MediaSources,Path",
                }, timeout=10).json().get("Items", [])
                
                parsed_items = []
                for d in details:
                    is_exempt = 1 if d.get("IndexNumberEnd") and d.get("IndexNumberEnd") > d.get("IndexNumber", 0) else 0
                    media_sources = d.get("MediaSources", [])
                    
                    if not media_sources: continue
                    
                    # 🔥 修复关键：全面遍历所有媒体源，不再只提取 [0]
                    for idx, src in enumerate(media_sources):
                        score, tags = calculate_score(src, strategy, custom_weights)

                        full_path = src.get("Path", "")
                        file_name = full_path.split("/")[-1].split("\\")[-1] if full_path else d.get("Name", "未知文件")
                        # 提取分组键中的ID（兼容多种格式）
                        if g_key.startswith("movie_tmdb_"):
                            tmdb_val = g_key.replace("movie_tmdb_", "")
                        elif g_key.startswith("movie_imdb_"):
                            tmdb_val = g_key.replace("movie_imdb_", "")
                        elif g_key.startswith("movie_name_"):
                            tmdb_val = g_key.replace("movie_name_", "")
                        elif g_key.startswith("tv_"):
                            # tv_{tmdb}_sXeY 或 tv_name_{name}_sXeY 或 tv_id_{id}_sXeY
                            parts = g_key.split("_s")
                            if len(parts) >= 2:
                                tmdb_val = parts[0].replace("tv_", "")
                            else:
                                tmdb_val = g_key.replace("tv_", "")
                        else:
                            tmdb_val = g_key

                        # 生成复合定向 ID，确保在多版本合并状态下，能精确且安全地删除副版本，而不伤及主版本
                        source_id = src.get("Id")
                        if idx == 0 or not source_id or source_id == d["Id"]:
                            composite_id = d["Id"]  # 主线本体
                        else:
                            composite_id = f"{d['Id']}__{source_id}"  # 隐藏的副本分支
                        
                        parsed_items.append({
                            "g_key": g_key, "tmdb": str(tmdb_val),
                            "mtype": d.get("Type"), "title": d.get("SeriesName") or d.get("Name", ""),
                            "season": d.get("ParentIndexNumber", 0), "episode": d.get("IndexNumber", 0),
                            "item_id": composite_id, "file_name": file_name, "file_path": full_path,
                            "res": tags["res"], "bitrate": src.get("Bitrate") or 0, "size": src.get("Size") or 0,
                            "v_codec": tags["v_codec"], "a_codec": tags["a_codec"],
                            "hdr": tags["has_hdr"], "dovi": tags["has_dovi"], "chi": tags["has_chi"], "ass": tags["has_ass"],
                            "score": score, "exempt": is_exempt
                        })

                if parsed_items:
                    parsed_items.sort(key=lambda x: x["score"], reverse=True)
                    top_score = parsed_items[0]["score"]
                    for idx, pi in enumerate(parsed_items):
                        pi["del_mark"] = 1 if idx > 0 and (top_score - pi["score"] >= 10) and pi["exempt"] == 0 else 0

                    for pi in parsed_items:
                        result_writer.insert_result(pi)
                result_writer.commit()
                time.sleep(0.02)
        elapsed = time.time() - start_time
        logger.info(f"✅ [去重引擎] 扫描完成！共遍历 {scan_state['total_items']} 个资源，发现 {scan_state['duplicate_groups']} 组重复。耗时: {elapsed:.2f} 秒。")
        scan_state["message"] = f"✅ 扫描完成！遍历 {scan_state['total_items']} 项，发现 {scan_state['duplicate_groups']} 组重复"
        
    except Exception as e:
        logger.error(f"[去重引擎] 扫描异常: {e}")
        scan_state["message"] = safe_error_message(e, "❌ 扫描失败")
    finally:
        time.sleep(2) 
        scan_state["is_scanning"] = False

class ScanReq(BaseModel):
    strategy: str = "quality"
    custom_weights: Optional[Dict[str, int]] = None
    excluded_libraries: Optional[List[str]] = None

class DeleteReq(BaseModel):
    item_ids: List[str]
    username: str
    password: str

class IgnoreItem(BaseModel):
    group_key: str
    title: str

class IgnoreReq(BaseModel):
    items: List[IgnoreItem]

class RemoveWhitelistReq(BaseModel):
    group_keys: List[str]

@router.post("/scan")
async def trigger_scan(request: Request, req: ScanReq, bg_tasks: BackgroundTasks):
    # 🔒 管理员专用
    if not user_service.is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}
    if scan_state["is_scanning"]: return {"success": False, "msg": "系统正在扫描中，请勿重复提交"}
    bg_tasks.add_task(run_dedupe_scan, req.strategy, req.custom_weights, req.excluded_libraries)
    return {"success": True, "msg": "🚀 扫描任务已在后台启动！"}

@router.get("/libraries")
async def get_dedupe_libraries(request: Request):
    # 🔒 管理员专用
    if not user_service.is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}
    """获取所有媒体库列表（用于去重管理）"""
    try:
        # 使用 /Library/VirtualFolders API 获取媒体库（更可靠）
        lib_res = media_api.get("/Library/VirtualFolders", timeout=10)
        
        if lib_res.status_code != 200:
            logger.error(f"[去重管理] 获取媒体库失败: HTTP {lib_res.status_code}")
            return {"success": False, "msg": f"媒体服务器返回 {lib_res.status_code}"}
        
        libraries = lib_res.json()
        logger.info(f"[去重管理] 获取到 {len(libraries)} 个媒体库: {[lib.get('Name') for lib in libraries]}")

        # 获取管理员用户ID用于统计项目数量
        admin_res = media_api.get("/Users", timeout=5).json()
        admin_id = next((u['Id'] for u in admin_res if u.get("Policy", {}).get("IsAdministrator")), admin_res[0]['Id'] if admin_res else None)

        result = []
        for lib in libraries:
            lib_id = lib.get("Guid") or lib.get("Id")
            lib_name = lib.get("Name", "未知")
            
            # 统计该媒体库下的电影和剧集数量
            total_count = 0
            if admin_id and lib_id:
                try:
                    count_res = media_api.get(f"/Users/{admin_id}/Items", params={
                        "ParentId": lib_id,
                        "IncludeItemTypes": "Movie,Episode",
                        "Recursive": "true",
                        "Limit": 1,
                    }, timeout=5).json()
                    total_count = count_res.get("TotalRecordCount", 0)
                except:
                    pass

            result.append({
                "id": lib_id,
                "name": lib_name,
                "item_count": total_count
            })

        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"[去重管理] 获取媒体库失败: {e}")
        return {"success": False, "msg": safe_error_message(e)}

@router.get("/status")
async def get_scan_status(request: Request):
    # 🔒 管理员专用
    if not user_service.is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}
    return {"success": True, "data": scan_state}

@router.get("/results")
async def get_results(request: Request):
    # 🔒 管理员专用
    if not user_service.is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}
    rows = list_dedupe_results()
    result_tree = defaultdict(list)
    if rows:
        for r in rows: result_tree[r["group_key"]].append(dict(r))
        
    base_url = get_media_server_main_public_or_host()
    if base_url.endswith('/'): base_url = base_url[:-1]
    
    server_id = ""
    try:
        info_res = media_api.get("/System/Info", timeout=2).json()
        raw_id = info_res.get("Id", "")
        if raw_id:
            server_id = str(raw_id).replace('\r', '').replace('\n', '').strip()
            
        if not server_id:
            item_res = media_api.get("/Items", params={"Limit": 1}, timeout=2).json()
            if item_res.get("Items"): 
                raw_id_2 = item_res["Items"][0].get("ServerId", "")
                if raw_id_2:
                    server_id = str(raw_id_2).replace('\r', '').replace('\n', '').strip()
    except Exception: pass
    
    return {"success": True, "data": result_tree, "emby_url": base_url, "server_id": server_id}

@router.post("/ignore")
async def ignore_groups(request: Request, req: IgnoreReq):
    # 🔒 管理员专用
    if not user_service.is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}
    try:
        add_dedupe_whitelist_items(req.items)
        return {"success": True, "msg": "已加入永久白名单"}
    except Exception as e: return {"success": False, "msg": safe_error_message(e)}

@router.get("/whitelist")
async def get_whitelist(request: Request):
    # 🔒 管理员专用
    if not user_service.is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}
    rows = list_dedupe_whitelist()
    return {"success": True, "data": [dict(r) for r in rows] if rows else []}

@router.post("/whitelist/remove")
async def remove_whitelist(request: Request, req: RemoveWhitelistReq):
    # 🔒 管理员专用
    if not user_service.is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}
    try:
        remove_dedupe_whitelist_items(req.group_keys)
        return {"success": True, "msg": "已移出白名单"}
    except Exception as e: return {"success": False, "msg": safe_error_message(e)}

@router.post("/delete")
async def delete_items(request: Request, req: DeleteReq):
    # 🔒 管理员专用
    if not user_service.is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}
    try:
        auth_res = media_api.authenticate_by_name(req.username, req.password, timeout=5)
        if auth_res.status_code != 200: return {"success": False, "msg": "🚫 权限被拒绝：Emby 管理员账号或密码错误！"}
        user_info = auth_res.json().get("User", {})
        if not user_info.get("Policy", {}).get("IsAdministrator"): return {"success": False, "msg": "🚫 权限被拒绝：该账号不具备管理员权限！"}
    except Exception as e: return {"success": False, "msg": f"⚠️ 连接 Emby 安全验证服务器失败: {e}"}
    
    success_count = 0; fail_count = 0
    for composite_id in req.item_ids:
        try:
            # 🔥 修复关键：调用专用的 AlternateSources 删除接口，安全抹除副版本物理文件
            if "__" in composite_id:
                item_id, source_id = composite_id.split("__")
                res = media_api.delete(f"/Videos/{item_id}/AlternateSources", params={"AlternateSourceId": source_id}, timeout=10)
            else:
                res = media_api.delete(f"/Items/{composite_id}", timeout=10)
                
            if res.status_code in [200, 204]:
                success_count += 1
                delete_dedupe_result_by_item_id(composite_id)
            else: 
                fail_count += 1
        except: 
            fail_count += 1
            
    return {"success": True, "msg": f"操作完成。成功物理删除 {success_count} 个文件，失败 {fail_count} 个。"}


# ==========================================
# 扫描配置保存/读取
# ==========================================
@router.get("/config")
async def get_dedupe_config(request: Request):
    # 🔒 管理员专用
    if not user_service.is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}
    """获取保存的扫描配置"""
    try:
        config = get_dedupe_config_values()
        return {"success": True, "data": config}
    except Exception as e:
        return {"success": False, "msg": safe_error_message(e)}

class ConfigItem(BaseModel):
    key: str
    value: str

class SaveConfigReq(BaseModel):
    config: Dict[str, Any]

@router.post("/config")
async def save_dedupe_config(request: Request, req: SaveConfigReq):
    # 🔒 管理员专用
    if not user_service.is_admin_user(request):
        return {"success": False, "msg": "需要管理员权限"}
    """保存扫描配置"""
    try:
        save_dedupe_config_values(req.config)
        return {"success": True, "msg": "配置已保存"}
    except Exception as e:
        return {"success": False, "msg": safe_error_message(e)}
