import logging
import re
import threading
import time

from app.core.security_utils import safe_error_message
from app.domains.media_requests.gap_dao import get_gap_config_map, save_gap_record_status
from app.domains.users import public_service as user_service
from app.infra.clients.moviepilot_client import moviepilot_client
from app.infra.clients.qbittorrent_client import qbittorrent_client
from app.infra.clients.transmission_client import transmission_client
from app.infra.config.moviepilot_settings import get_moviepilot_token, get_moviepilot_url


logger = logging.getLogger("uvicorn")

_logger_provider = lambda: logger
_moviepilot_url_provider = lambda: get_moviepilot_url()
_moviepilot_token_provider = lambda: get_moviepilot_token()
_moviepilot_client_provider = lambda: moviepilot_client
_qbittorrent_client_provider = lambda: qbittorrent_client
_transmission_client_provider = lambda: transmission_client
_gap_config_map_provider = lambda: get_gap_config_map()
_save_gap_record_status_provider = lambda: save_gap_record_status
_scan_state_provider = lambda: {"results": []}
_state_lock_provider = lambda: threading.Lock()
_user_is_admin_provider = lambda request: user_service.is_admin_user(request)
_thread_factory_provider = lambda: threading.Thread
_time_provider = lambda: time
_hook_qbittorrent_provider = lambda: hook_qbittorrent
_hook_transmission_provider = lambda: hook_transmission


def set_dependency_providers(
    *,
    logger_provider=None,
    moviepilot_url_provider=None,
    moviepilot_token_provider=None,
    moviepilot_client_provider=None,
    qbittorrent_client_provider=None,
    transmission_client_provider=None,
    gap_config_map_provider=None,
    save_gap_record_status_provider=None,
    scan_state_provider=None,
    state_lock_provider=None,
    user_is_admin_provider=None,
    thread_factory_provider=None,
    time_provider=None,
    hook_qbittorrent_provider=None,
    hook_transmission_provider=None,
):
    global _logger_provider
    global _moviepilot_url_provider
    global _moviepilot_token_provider
    global _moviepilot_client_provider
    global _qbittorrent_client_provider
    global _transmission_client_provider
    global _gap_config_map_provider
    global _save_gap_record_status_provider
    global _scan_state_provider
    global _state_lock_provider
    global _user_is_admin_provider
    global _thread_factory_provider
    global _time_provider
    global _hook_qbittorrent_provider
    global _hook_transmission_provider

    if logger_provider is not None:
        _logger_provider = logger_provider
    if moviepilot_url_provider is not None:
        _moviepilot_url_provider = moviepilot_url_provider
    if moviepilot_token_provider is not None:
        _moviepilot_token_provider = moviepilot_token_provider
    if moviepilot_client_provider is not None:
        _moviepilot_client_provider = moviepilot_client_provider
    if qbittorrent_client_provider is not None:
        _qbittorrent_client_provider = qbittorrent_client_provider
    if transmission_client_provider is not None:
        _transmission_client_provider = transmission_client_provider
    if gap_config_map_provider is not None:
        _gap_config_map_provider = gap_config_map_provider
    if save_gap_record_status_provider is not None:
        _save_gap_record_status_provider = save_gap_record_status_provider
    if scan_state_provider is not None:
        _scan_state_provider = scan_state_provider
    if state_lock_provider is not None:
        _state_lock_provider = state_lock_provider
    if user_is_admin_provider is not None:
        _user_is_admin_provider = user_is_admin_provider
    if thread_factory_provider is not None:
        _thread_factory_provider = thread_factory_provider
    if time_provider is not None:
        _time_provider = time_provider
    if hook_qbittorrent_provider is not None:
        _hook_qbittorrent_provider = hook_qbittorrent_provider
    if hook_transmission_provider is not None:
        _hook_transmission_provider = hook_transmission_provider


def extract_episodes_from_filename(filename: str) -> set:
    """从文件名中提取集数，支持多种命名格式"""
    eps = set()
    fname = filename.upper()

    s_e = re.findall(r"S\d{1,2}E(\d{1,3})(?:-E?(\d{1,3}))?", fname)
    for e1, e2 in s_e:
        eps.add(int(e1))
        if e2:
            eps.update(range(int(e1), int(e2) + 1))

    ep = re.findall(r"(?:EPISODE|EP|E)[\s\.\-]*(\d{1,3})(?:-E?(\d{1,3}))?", fname)
    for e1, e2 in ep:
        eps.add(int(e1))
        if e2:
            eps.update(range(int(e1), int(e2) + 1))

    zh = re.findall(r"第\s*(\d{1,3})\s*(?:-|至|到)\s*(\d{1,3})\s*集", filename)
    for e1, e2 in zh:
        eps.update(range(int(e1), int(e2) + 1))
    zh_single = re.findall(r"第\s*(\d{1,3})\s*集", filename)
    for e in zh_single:
        eps.add(int(e))

    if not eps:
        naked = re.findall(r"(?:\[|\s-?\s|\.)(\d{2,4})(?:\]|\s|\.)", fname)
        for e in naked:
            num = int(e)
            if num not in (480, 720, 1080, 2160, 264, 265, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027):
                eps.add(num)

    if not eps:
        prefix = re.match(r"^(\d{1,3})(?:-(\d{1,3}))?\s*[\.\[]", filename)
        if prefix:
            eps.add(int(prefix.group(1)))
            if prefix.group(2):
                eps.update(range(int(prefix.group(1)), int(prefix.group(2)) + 1))

    return eps


def hook_qbittorrent(host, user, password, expected_size, target_episodes, torrent_name=None):
    """
    qBittorrent 截胡功能
    :param host: QB WebUI 地址
    :param user: 用户名
    :param password: 密码
    :param expected_size: 预期种子大小（字节）
    :param target_episodes: 目标集数列表
    :param torrent_name: 种子名称关键词（用于辅助匹配）
    """
    qb_client = _qbittorrent_client_provider()
    time_module = _time_provider()
    logger_obj = _logger_provider()
    try:
        s = qb_client.create_session()
        login = qb_client.login(s, host, user, password, timeout=10)
        if login.status_code != 200 or "Ok" not in login.text:
            logger_obj.error(f"[QB截胡] 登录失败: status={login.status_code}, response={login.text[:100]}")
            return False, "qBittorrent 登录失败"

        target_hash = None
        target_torrent = None
        logger_obj.info(f"[QB截胡] 开始轮询，expected_size={expected_size}, target_episodes={target_episodes}, torrent_name={torrent_name}")

        for attempt in range(20):
            time_module.sleep(3)
            res = qb_client.list_torrents(s, host, timeout=10)
            if res.status_code != 200:
                logger_obj.warning(f"[QB截胡] 获取种子列表失败: status={res.status_code}")
                continue

            torrents = res.json()
            logger_obj.debug(f"[QB截胡] 第 {attempt+1} 次轮询，找到 {len(torrents)} 个种子")

            for t in torrents:
                age = time_module.time() - t.get("added_on", 0)
                if age > 300:
                    continue

                t_size = t.get("total_size", 0)
                t_name = t.get("name", "")
                t_hash = t.get("hash", "")

                if expected_size > 0 and abs(t_size - expected_size) < 100 * 1024 * 1024:
                    target_hash = t_hash
                    target_torrent = t
                    logger_obj.info(f"[QB截胡] 大小匹配成功: {t_name}, size={t_size}, expected={expected_size}, diff={abs(t_size-expected_size)/1024/1024:.1f}MB")
                    break

                if torrent_name and torrent_name.lower() in t_name.lower():
                    target_hash = t_hash
                    target_torrent = t
                    logger_obj.info(f"[QB截胡] 名称匹配成功: {t_name}, 关键词={torrent_name}")
                    break

            if target_hash:
                break

            if expected_size == 0 and torrents:
                for t in torrents:
                    age = time_module.time() - t.get("added_on", 0)
                    if age <= 300:
                        target_hash = t.get("hash")
                        target_torrent = t
                        logger_obj.info(f"[QB截胡] 回退到最新种子: {t.get('name')}, age={int(age)}s")
                        break
                if target_hash:
                    break

        if not target_hash:
            return False, "轮询 60 秒超时：未找到匹配的种子"

        f_res = qb_client.list_files(s, host, target_hash, timeout=10)
        if f_res.status_code != 200:
            logger_obj.error(f"[QB截胡] 获取文件列表失败: status={f_res.status_code}")
            return False, f"获取种子文件列表失败 (HTTP {f_res.status_code})"

        files = f_res.json()
        if not files:
            return False, "种子文件列表为空"

        logger_obj.info(f"[QB截胡] 种子 '{target_torrent.get('name')}' 包含 {len(files)} 个文件")

        if len(files) == 1:
            fname = files[0].get("name", "")
            logger_obj.info(f"[QB截胡] 单文件种子: {fname}")
            return True, "📦 单文件种子，无需截胡"

        wanted, unwanted, wanted_names, unwanted_names = [], [], [], []
        video_extensions = (".mp4", ".mkv", ".avi", ".ts", ".iso", ".wmv", ".flv", ".m2ts", ".vob")

        for i, f in enumerate(files):
            fname = f.get("name", "")
            if not fname.lower().endswith(video_extensions):
                unwanted.append(str(i))
                unwanted_names.append(fname)
                logger_obj.debug(f"[QB截胡] 跳过非视频文件: {fname}")
                continue

            f_eps = extract_episodes_from_filename(fname)
            logger_obj.debug(f"[QB截胡] 文件 '{fname}' 识别集数: {f_eps}")

            is_wanted = any(e in target_episodes for e in f_eps)
            if is_wanted:
                wanted.append(str(i))
                wanted_names.append(f"{fname} (集数:{f_eps})")
            else:
                unwanted.append(str(i))
                unwanted_names.append(f"{fname} (集数:{f_eps})")

        logger_obj.info(f"[QB截胡] 匹配结果: wanted={len(wanted)}, unwanted={len(unwanted)}")
        logger_obj.info(f"[QB截胡] 想要的文件: {wanted_names}")
        logger_obj.info(f"[QB截胡] 不想要的文件: {unwanted_names}")

        if not wanted:
            logger_obj.warning(f"[QB截胡] 未能识别出目标集数，target_episodes={target_episodes}")
            return False, "⚠️ 未能识别出目标集数，为防止误删已放行全包下载"

        if not unwanted:
            return True, f"✅ 种子内所有 {len(wanted)} 个视频文件均为目标集数，无需截胡"

        try:
            if unwanted:
                prio_res = qb_client.set_file_priority(s, host, target_hash, "|".join(unwanted), 0, timeout=10)
                logger_obj.info(f"[QB截胡] 设置不下载文件: {unwanted}, 响应: {prio_res.status_code}")

            if wanted:
                prio_res = qb_client.set_file_priority(s, host, target_hash, "|".join(wanted), 1, timeout=10)
                logger_obj.info(f"[QB截胡] 设置下载文件: {wanted}, 响应: {prio_res.status_code}")

            return True, f"🔪 截胡成功！保留 {len(wanted)} 个目标文件，跳过 {len(unwanted)} 个多余文件"

        except Exception as e:
            logger_obj.error(f"[QB截胡] 设置文件优先级失败: {e}")
            return False, safe_error_message(e, "设置文件优先级失败")

    except qb_client.Timeout:
        logger_obj.error("[QB截胡] 连接超时")
        return False, "qBittorrent 连接超时，请检查网络"
    except qb_client.ConnectionError:
        logger_obj.error("[QB截胡] 连接失败")
        return False, "qBittorrent 连接失败，请检查地址是否正确"
    except Exception as e:
        logger_obj.error(f"[QB截胡] 异常: {e}", exc_info=True)
        return False, safe_error_message(e, "qB 交互异常")


def hook_transmission(host, user, password, expected_size, target_episodes):
    tr_client = _transmission_client_provider()
    time_module = _time_provider()
    try:
        auth = (user, password) if user else None
        s = tr_client.create_session()
        res = tr_client.handshake(s, host, auth=auth, timeout=10)
        session_id = res.headers.get("X-Transmission-Session-Id")
        if not session_id:
            return False, "Transmission 认证失败"
        s.headers.update({"X-Transmission-Session-Id": session_id})
        target_id = None
        for _attempt in range(20):
            time_module.sleep(3)
            payload = {"method": "torrent-get", "arguments": {"fields": ["id", "addedDate", "totalSize", "files"]}}
            r = tr_client.torrent_get(s, host, payload, auth=auth, timeout=10)
            if r.status_code == 200:
                torrents = r.json().get("arguments", {}).get("torrents", [])
                for t in torrents:
                    if time_module.time() - t.get("addedDate", 0) < 300:
                        if expected_size > 0 and abs(t.get("totalSize", 0) - expected_size) < 10 * 1024 * 1024:
                            target_id = t.get("id")
                            files = t.get("files", [])
                            break
            if target_id and files and len(files) > 0 and files[0].get("length", 0) > 0:
                wanted, unwanted = [], []
                for i, f in enumerate(files):
                    fname = f.get("name", "")
                    if not fname.lower().endswith((".mp4", ".mkv", ".avi", ".ts", ".iso")):
                        unwanted.append(i)
                        continue
                    f_eps = extract_episodes_from_filename(fname)
                    if any(e in target_episodes for e in f_eps):
                        wanted.append(i)
                    else:
                        unwanted.append(i)
                if not wanted:
                    return False, "⚠️ 正则未匹配到视频集数，为防止误杀，已放行全包下载"
                set_payload = {"method": "torrent-set", "arguments": {"id": target_id}}
                if unwanted:
                    set_payload["arguments"]["files-unwanted"] = unwanted
                if wanted:
                    set_payload["arguments"]["files-wanted"] = wanted
                tr_client.torrent_get(s, host, set_payload, auth=auth, timeout=10)
                return True, f"🔪 TR 截胡成功！保留 {len(wanted)} 集，剔除 {len(unwanted)} 个文件"
        return False, "轮询 60 秒超时：未锁定种子"
    except Exception as e:
        return False, safe_error_message(e, "TR 交互异常")


def _normalize_torrent_info(torrent_info):
    pure_torrent_in = torrent_info.get("org_payload", torrent_info)
    try:
        pure_torrent_in["size"] = int(float(pure_torrent_in.get("size", 0)))
    except Exception:
        pure_torrent_in["size"] = 0
    return pure_torrent_in


def _update_successful_download_state(series_id, series_name, season, episodes):
    for ep in episodes:
        _save_gap_record_status_provider()(series_id, series_name, int(season), int(ep), 2)

    scan_state = _scan_state_provider()
    with _state_lock_provider():
        for s in scan_state["results"]:
            if s.get("series_id") == series_id:
                for ep_obj in s.get("gaps", []):
                    if ep_obj["season"] == int(season) and ep_obj["episode"] in [int(e) for e in episodes]:
                        ep_obj["status"] = 2


def _run_interception(client_type, client_url, client_user, client_pass, pure_torrent_in, episodes, torrent_name):
    if not client_type or not client_url or len(episodes) <= 0:
        return

    expected_size = pure_torrent_in.get("size", 0)
    logger_obj = _logger_provider()
    try:
        if client_type == "qbittorrent":
            success, msg = _hook_qbittorrent_provider()(client_url, client_user, client_pass, expected_size, episodes, torrent_name)
        elif client_type == "transmission":
            success, msg = _hook_transmission_provider()(client_url, client_user, client_pass, expected_size, episodes)
        else:
            return
        logger_obj.info(f"[缺集下载] 截胡完成: success={success}, msg={msg}")
    except Exception as e:
        logger_obj.error(f"[缺集下载] 截胡异常: {e}")


def _download_async(series_id, series_name, season, episodes, mp_url, mp_token, mp_payload, pure_torrent_in, client_config, torrent_name):
    logger_obj = _logger_provider()
    try:
        res = _moviepilot_client_provider().add_download(mp_url, mp_token, mp_payload, timeout=60)
        if res.status_code in [200, 201]:
            logger_obj.info(f"[缺集下载] MP推送成功: {series_name} S{season}E{episodes}")
            _update_successful_download_state(series_id, series_name, season, episodes)
            _run_interception(
                client_config["client_type"],
                client_config["client_url"],
                client_config["client_user"],
                client_config["client_pass"],
                pure_torrent_in,
                episodes,
                torrent_name,
            )
        else:
            logger_obj.error(f"[缺集下载] MP推送失败: HTTP {res.status_code}, {res.text[:200]}")
    except Exception as e:
        logger_obj.error(f"[缺集下载] 异步下载异常: {e}")


def download_gap_item(request=None, payload=None):
    if request and not _user_is_admin_provider(request):
        return {"status": "error", "message": "需要管理员权限"}

    series_id = payload.get("series_id") if payload else None
    series_name = payload.get("series_name") if payload else None
    season = payload.get("season") if payload else None
    episodes = payload.get("episodes", []) if payload else []
    torrent_info = payload.get("torrent_info", {}) if payload else {}

    mp_url = _moviepilot_url_provider()
    mp_token = _moviepilot_token_provider()
    ui_conf = _gap_config_map_provider()

    client_config = {
        "client_type": ui_conf.get("client_type", ""),
        "client_url": ui_conf.get("client_url", ""),
        "client_user": ui_conf.get("client_user", ""),
        "client_pass": ui_conf.get("client_pass", ""),
    }

    pure_torrent_in = _normalize_torrent_info(torrent_info)
    torrent_name = pure_torrent_in.get("title") or pure_torrent_in.get("name") or pure_torrent_in.get("enclosure_name")
    mp_payload = {"torrent_in": pure_torrent_in}

    thread = _thread_factory_provider()(
        target=lambda: _download_async(
            series_id,
            series_name,
            season,
            episodes,
            mp_url,
            mp_token,
            mp_payload,
            pure_torrent_in,
            client_config,
            torrent_name,
        ),
        daemon=True,
    )
    thread.start()

    return {"status": "success", "message": "种子已提交到后台队列，正在处理..."}
