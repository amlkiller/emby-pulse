from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.config import REPORT_COVER_URL
from app.core.security_utils import safe_error_message
from app.domains.media_requests.discovery_router import get_tmdb_season_info
from app.domains.media_requests.media_request_dao import (
    get_update_request_search_info,
    submit_batch_update_request_records,
    submit_update_request_record,
    update_media_request_status,
)
from app.domains.notifications import public_service as notification_service
from app.domains.users import public_service as user_service
from app.infra.clients.tmdb_client import tmdb_client
from app.infra.config.media_server_settings import get_media_server_main_public_url
from app.infra.config.request_portal_settings import get_pulse_url
from app.infra.db.notification_dao import add_system_notification
from app.utils.proxy_helper import get_safe_proxies


router = APIRouter()

_user_service_provider = lambda: user_service
_check_user_exists_provider = lambda: lambda user_id: True
_get_tmdb_season_info_provider = lambda: get_tmdb_season_info
_submit_update_request_record_provider = lambda: submit_update_request_record
_submit_batch_update_request_records_provider = lambda: submit_batch_update_request_records
_safe_proxies_provider = lambda: get_safe_proxies
_tmdb_client_provider = lambda: tmdb_client
_system_notification_provider = lambda: add_system_notification
_notification_service_provider = lambda: notification_service
_pulse_url_provider = lambda: get_pulse_url
_media_server_public_url_provider = lambda: get_media_server_main_public_url
_report_cover_url_provider = lambda: REPORT_COVER_URL
_get_update_request_search_info_provider = lambda: get_update_request_search_info
_update_media_request_status_provider = lambda: update_media_request_status
_safe_error_message_provider = lambda: safe_error_message


def _default_gap_search_provider():
    from app.domains.media_requests.gaps import search_mp_for_gap

    return search_mp_for_gap


def _default_gap_download_provider():
    from app.domains.media_requests.gaps import download_gap_item

    return download_gap_item


_gap_search_provider = _default_gap_search_provider
_gap_download_provider = _default_gap_download_provider


class UpdateRequestModel(BaseModel):
    """追新请求模型"""
    series_id: str
    tmdb_id: int
    title: str
    year: Optional[str] = ""
    poster_path: Optional[str] = ""
    season: int
    episodes: List[int]  # 请求的集数列表


def set_dependency_providers(
    *,
    user_service_provider=None,
    check_user_exists_provider=None,
    get_tmdb_season_info_provider=None,
    submit_update_request_record_provider=None,
    submit_batch_update_request_records_provider=None,
    safe_proxies_provider=None,
    tmdb_client_provider=None,
    system_notification_provider=None,
    notification_service_provider=None,
    pulse_url_provider=None,
    media_server_public_url_provider=None,
    report_cover_url_provider=None,
    get_update_request_search_info_provider=None,
    update_media_request_status_provider=None,
    safe_error_message_provider=None,
    gap_search_provider=None,
    gap_download_provider=None,
):
    global _user_service_provider
    global _check_user_exists_provider
    global _get_tmdb_season_info_provider
    global _submit_update_request_record_provider
    global _submit_batch_update_request_records_provider
    global _safe_proxies_provider
    global _tmdb_client_provider
    global _system_notification_provider
    global _notification_service_provider
    global _pulse_url_provider
    global _media_server_public_url_provider
    global _report_cover_url_provider
    global _get_update_request_search_info_provider
    global _update_media_request_status_provider
    global _safe_error_message_provider
    global _gap_search_provider
    global _gap_download_provider

    if user_service_provider is not None:
        _user_service_provider = user_service_provider
    if check_user_exists_provider is not None:
        _check_user_exists_provider = check_user_exists_provider
    if get_tmdb_season_info_provider is not None:
        _get_tmdb_season_info_provider = get_tmdb_season_info_provider
    if submit_update_request_record_provider is not None:
        _submit_update_request_record_provider = submit_update_request_record_provider
    if submit_batch_update_request_records_provider is not None:
        _submit_batch_update_request_records_provider = submit_batch_update_request_records_provider
    if safe_proxies_provider is not None:
        _safe_proxies_provider = safe_proxies_provider
    if tmdb_client_provider is not None:
        _tmdb_client_provider = tmdb_client_provider
    if system_notification_provider is not None:
        _system_notification_provider = system_notification_provider
    if notification_service_provider is not None:
        _notification_service_provider = notification_service_provider
    if pulse_url_provider is not None:
        _pulse_url_provider = pulse_url_provider
    if media_server_public_url_provider is not None:
        _media_server_public_url_provider = media_server_public_url_provider
    if report_cover_url_provider is not None:
        _report_cover_url_provider = report_cover_url_provider
    if get_update_request_search_info_provider is not None:
        _get_update_request_search_info_provider = get_update_request_search_info_provider
    if update_media_request_status_provider is not None:
        _update_media_request_status_provider = update_media_request_status_provider
    if safe_error_message_provider is not None:
        _safe_error_message_provider = safe_error_message_provider
    if gap_search_provider is not None:
        _gap_search_provider = gap_search_provider
    if gap_download_provider is not None:
        _gap_download_provider = gap_download_provider


# 🔥 辅助函数：获取请求状态文本（同步版本）
def getRequestStatusTextSync(status):
    status_map = {0: '待审批', 1: '下载中', 2: '已完成', 3: '已拒绝', 4: '手动接单', 7: '待入库'}
    return status_map.get(status, '未知')


@router.post("/api/user/request_update")
async def submit_update_request(request: Request):
    """提交追新请求"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}

    if not _check_user_exists_provider()(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除", "account_deleted": True}

    uid = user['Id']
    uname = user['Name']

    try:
        data = await request.json()
        series_id = data.get("series_id")
        tmdb_id = int(data.get("tmdb_id") or 0)
        title = data.get("title")
        year = data.get("year", "")
        poster_path = data.get("poster_path", "")
        season = int(data.get("season") or 0)
        episodes = data.get("episodes", [])  # 列表 [6, 7, 8]

        if not tmdb_id or not season or not episodes:
            return {"status": "error", "message": "参数不完整"}

        # 验证集数
        episodes = [int(e) for e in episodes if int(e) > 0]
        if not episodes:
            return {"status": "error", "message": "请选择有效的集数"}

        # 🔥 检查未播出集数（禁止追更未播出的剧集）
        _, unaired_eps = _get_tmdb_season_info_provider()(tmdb_id, season)
        unaired_requested = [e for e in episodes if e in unaired_eps]
        if unaired_requested:
            return {"status": "error", "message": f"以下集数尚未播出，无法追更：E{','.join(str(e) for e in unaired_requested)}"}

        result = _submit_update_request_record_provider()(uid, uname, series_id, tmdb_id, title, year, poster_path, season, episodes)
        if not result.get("ok"):
            return {"status": "error", "message": result.get("message", "提交失败")}
        episodes_str = result["episodes_str"]

        # 发送通知
        try:
            # 🔥 从 TMDB 获取年份（前端提交的 year 可能为空）
            actual_year = year
            if not actual_year or actual_year == "":
                try:
                    proxies = _safe_proxies_provider()()
                    tmdb_info = _tmdb_client_provider().get_tv_details(tmdb_id, proxies=proxies, timeout=5).json()
                    first_air_date = tmdb_info.get("first_air_date", "")
                    actual_year = first_air_date[:4] if first_air_date else ""
                except:
                    actual_year = ""

            year_display = f" ({actual_year})" if actual_year else ""

            _system_notification_provider()("request", f"收到追新请求: {title}",
                               f"用户 {uname} 请求更新 S{season}E{episodes_str}", "/requests_admin")

            msg = f"🔄 <b>收到追新请求</b>\n\n👤 <b>用户：</b>{uname}\n📺 <b>内容：</b>{title}{year_display}\n📀 <b>季集：</b>第 {season} 季 E{episodes_str.replace(',', '-')}集\n\n请及时处理。"

            admin_url = _pulse_url_provider()() or _media_server_public_url_provider()() or "http://127.0.0.1:10307"
            keyboard = {"inline_keyboard": [
                [{"text": "🔍 影巢搜索", "callback_data": f"req_hdhive_ep_{tmdb_id}_{season}_{episodes_str}_{title.replace('_', '-').replace(':', '').replace('：', '').replace(' ', '-')}"}],
                [{"text": "✋ 手动接单", "callback_data": f"req_manual_{tmdb_id}_{season}"}, {"text": "💻 网页审批", "url": f"{admin_url.rstrip('/')}/requests_admin"}]
            ]}

            # 🔥 处理封面路径：本地路径需要从 TMDB 获取
            poster_url = _report_cover_url_provider()
            if poster_path and poster_path.startswith("/api/"):
                # 本地 API 路径，从 TMDB 获取封面
                try:
                    proxies = _safe_proxies_provider()()
                    tmdb_info = _tmdb_client_provider().get_tv_details(tmdb_id, proxies=proxies, timeout=5).json()
                    tmdb_poster = tmdb_info.get("poster_path")
                    if tmdb_poster:
                        poster_url = f"https://image.tmdb.org/t/p/w500{tmdb_poster}"
                except:
                    pass
            elif poster_path and poster_path.startswith("/") and not poster_path.startswith("/api/"):
                # TMDB 相对路径
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            elif poster_path and poster_path.startswith("http"):
                # 完整 URL
                poster_url = poster_path

            _notification_service_provider().send_photo("sys_notify", poster_url, msg, reply_markup=keyboard, platform="all")
        except Exception as e:
            print(f"[追新] 发送通知失败: {e}")

        return {"status": "success", "message": f"追新请求已提交！等待管理员处理 S{season}E{episodes_str}"}

    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e, "提交失败")}


@router.post("/api/user/request_update_batch")
async def submit_update_request_batch(request: Request):
    """批量提交追新请求（一次扣费）"""
    user = request.session.get("req_user")
    if not user:
        return {"status": "error", "message": "未登录"}

    if not _check_user_exists_provider()(user.get("Id")):
        request.session.pop("req_user", None)
        return {"status": "error", "message": "账号已被删除", "account_deleted": True}

    uid = user['Id']
    uname = user['Name']

    try:
        data = await request.json()
        requests_list = data.get("requests", [])
        series_name = data.get("series_name", "")
        tmdb_id = int(data.get("tmdb_id") or 0)

        if not requests_list:
            return {"status": "error", "message": "没有追新请求"}

        result = _submit_batch_update_request_records_provider()(uid, uname, requests_list, series_name, tmdb_id)
        if not result.get("ok"):
            return {"status": "error", "message": result.get("message", "提交失败")}
        total_seasons = result["total_seasons"]
        total_episodes = result["total_episodes"]
        total_cost = result["total_cost"]
        cost_mode = result["cost_mode"]
        print(f"[追新批量] 模式={cost_mode}, 季数={total_seasons}, 集数={total_episodes}, 扣分={total_cost}")

        # 发送通知
        try:
            # 🔥 构建详细季集信息
            season_details = []
            for req in requests_list:
                req_season = req.get("season")
                req_episodes = req.get("episodes", [])
                if req_season and req_episodes:
                    eps_str = ",".join(str(e) for e in sorted(req_episodes))
                    season_details.append(f"第 {req_season} 季 E{eps_str.replace(',', '-')}集")

            season_detail_str = "\n".join(season_details)

            _system_notification_provider()("request", f"收到批量追新请求: {series_name}",
                               f"用户 {uname} 请求更新\n{season_detail_str}", "/requests_admin")

            # 🔥 从 TMDB 获取封面
            poster_url = _report_cover_url_provider()
            try:
                proxies = _safe_proxies_provider()()
                tmdb_info = _tmdb_client_provider().get_tv_details(tmdb_id, proxies=proxies, timeout=5).json()
                tmdb_poster = tmdb_info.get("poster_path")
                first_air_date = tmdb_info.get("first_air_date", "")
                year_display = f" ({first_air_date[:4]})" if first_air_date else ""
                if tmdb_poster:
                    poster_url = f"https://image.tmdb.org/t/p/w500{tmdb_poster}"
            except:
                year_display = ""

            msg = f"🔄 <b>收到批量追新请求</b>\n\n👤 <b>用户：</b>{uname}\n📺 <b>内容：</b>{series_name}{year_display}\n\n📀 <b>季集详情：</b>\n{season_detail_str}\n\n请及时处理。"

            admin_url = _pulse_url_provider()() or _media_server_public_url_provider()() or "http://127.0.0.1:10307"

            # 🔥 简化按钮：影巢搜索（标题）+ 手动接单 + 网页审批
            keyboard = {"inline_keyboard": [
                [{"text": "🔍 影巢搜索", "callback_data": f"req_hdhive_{tmdb_id}_{series_name.replace('_', '-').replace(':', '').replace('：', '').replace(' ', '-')}"}],
                [{"text": "✋ 手动接单", "callback_data": f"req_manual_{tmdb_id}_0"}, {"text": "💻 网页审批", "url": f"{admin_url.rstrip('/')}/requests_admin"}]
            ]}

            _notification_service_provider().send_photo("sys_notify", poster_url, msg, reply_markup=keyboard, platform="all")
        except Exception as e:
            print(f"[追新批量] 发送通知失败: {e}")

        return {"status": "success", "message": f"批量追新请求已提交！{total_seasons} 季 {total_episodes} 集"}

    except Exception as e:
        print(f"[追新批量] 错误: {e}")
        return {"status": "error", "message": _safe_error_message_provider()(e, "提交失败")}


@router.post("/api/manage/requests/search_episodes")
def search_episodes_for_update(payload: dict, request: Request):
    """搜索单集资源（追新工单使用，复用缺集搜索逻辑）"""
    # 🔒 安全检查：必须管理员
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "无权访问"}

    tmdb_id = payload.get("tmdb_id")
    season = payload.get("season")
    episodes = payload.get("episodes", [])

    if not tmdb_id or season is None or not episodes:
        return {"status": "error", "message": "参数不完整"}

    # 获取剧集名称 - 优先从数据库获取追新请求的标题
    row = _get_update_request_search_info_provider()(tmdb_id, season)

    series_name = row["title"] if row else "未知剧集"
    series_id = row["series_id"] if row else ""

    # 调用缺集搜索 API - 传递完整参数
    try:
        result = _gap_search_provider()({
            "series_name": series_name,
            "series_id": series_id,
            "tmdb_id": tmdb_id,
            "season": season,
            "episodes": episodes,
            "type": "tv"
        })
        # 转换返回格式，适配前端
        if result.get("status") == "success" and result.get("data"):
            raw_results = result["data"].get("results", [])
            # 确保返回完整的字段
            processed_results = []
            for r in raw_results:
                processed_results.append({
                    "ui_title": r.get("ui_title", r.get("title", "")),
                    "ui_size": r.get("ui_size", 0),
                    "ui_seeders": r.get("ui_seeders", 0),
                    "ui_extracted_episodes": r.get("ui_extracted_episodes", []),
                    "ui_matched_episodes": r.get("ui_matched_episodes", []),
                    "ui_site": r.get("ui_site", "MP"),
                    "ui_desc": r.get("ui_desc", ""),
                    "ui_resolution": r.get("ui_resolution", ""),
                    "ui_resource": r.get("ui_resource", ""),
                    "ui_labels": r.get("ui_labels", []),
                    "ui_chinese_audio": r.get("ui_chinese_audio", False),
                    "ui_chinese_sub": r.get("ui_chinese_sub", False),
                    "match_score": r.get("match_score", 0),
                    "is_pack": r.get("is_pack", False),
                    "enclosure": r.get("enclosure", ""),
                    "org_payload": r.get("org_payload", r)
                })
            return {"status": "success", "results": processed_results}
        return result
    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e, "搜索失败")}


@router.post("/api/manage/requests/download_episodes")
def download_episodes_for_update(payload: dict, request: Request):
    """下载单集资源（追新工单使用，复用缺集下载逻辑）"""
    # 🔒 安全检查：必须管理员
    if not _user_service_provider().is_admin_user(request):
        return {"status": "error", "message": "无权访问"}

    series_id = payload.get("series_id")
    series_name = payload.get("series_name")
    tmdb_id = payload.get("tmdb_id")
    season = payload.get("season")
    episodes = payload.get("episodes", [])
    torrent_info = payload.get("torrent_info", {})

    if not episodes:
        return {"status": "error", "message": "未指定集数"}

    # 调用缺集下载 API
    try:
        result = _gap_download_provider()({
            "series_id": series_id or "",
            "series_name": series_name,
            "tmdb_id": tmdb_id,
            "season": season,
            "episodes": episodes,
            "torrent_info": torrent_info
        })

        # 更新工单状态为下载中
        if result.get("status") == "success":
            episodes_str = ",".join(str(e) for e in episodes)
            # 更新所有匹配的追新工单
            _update_media_request_status_provider()(tmdb_id, season, 1)

        return result
    except Exception as e:
        return {"status": "error", "message": _safe_error_message_provider()(e, "下载失败")}
