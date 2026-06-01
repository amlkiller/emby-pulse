import json

from app.infra.db.schema_bootstrap import ensure_registered_table
from app.infra.db.row import to_data_row
from app.infra.db.system_store import system_store


def ensure_media_request_schema() -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(media_requests)")
        columns = cursor.fetchall()
        if columns:
            pk_columns = [column[1] for column in columns if column[5] > 0]
            if "season" not in pk_columns:
                cursor.execute("ALTER TABLE media_requests RENAME TO media_requests_old")
                cursor.execute(
                    """
                    CREATE TABLE media_requests (
                        tmdb_id INTEGER, media_type TEXT, title TEXT, year TEXT, poster_path TEXT,
                        status INTEGER DEFAULT 0, season INTEGER DEFAULT 0, reject_reason TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (tmdb_id, season)
                    )
                    """
                )
                cursor.execute(
                    "INSERT OR IGNORE INTO media_requests (tmdb_id, media_type, title, year, poster_path, status, season, reject_reason, created_at) SELECT tmdb_id, media_type, title, year, poster_path, status, 0, reject_reason, created_at FROM media_requests_old"
                )
                cursor.execute("DROP TABLE media_requests_old")

        cursor.execute("PRAGMA table_info(media_requests)")
        request_columns = [column[1] for column in cursor.fetchall()]
        if "episodes" not in request_columns:
            try:
                cursor.execute("ALTER TABLE media_requests ADD COLUMN episodes TEXT DEFAULT ''")
            except Exception:
                pass
        if "request_type" not in request_columns:
            try:
                cursor.execute("ALTER TABLE media_requests ADD COLUMN request_type TEXT DEFAULT 'new'")
            except Exception:
                pass
        if "series_id" not in request_columns:
            try:
                cursor.execute("ALTER TABLE media_requests ADD COLUMN series_id TEXT DEFAULT ''")
            except Exception:
                pass

        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='request_users'")
        user_table = cursor.fetchone()
        if user_table:
            sql = user_table[0].lower().replace(" ", "")
            if "unique(tmdb_id,user_id,season)" not in sql:
                cursor.execute("ALTER TABLE request_users RENAME TO request_users_old")
                cursor.execute(
                    """
                    CREATE TABLE request_users (
                        tmdb_id INTEGER, user_id TEXT, username TEXT, season INTEGER DEFAULT 0,
                        requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(tmdb_id, user_id, season)
                    )
                    """
                )
                cursor.execute(
                    "INSERT OR IGNORE INTO request_users (tmdb_id, user_id, username, season) SELECT tmdb_id, user_id, COALESCE(username, '系统用户'), COALESCE(season, 0) FROM request_users_old"
                )
                cursor.execute("DROP TABLE request_users_old")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS media_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT,
                user_id TEXT,
                username TEXT,
                issue_type TEXT,
                description TEXT,
                status INTEGER DEFAULT 0,
                poster_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute("PRAGMA table_info(media_feedback)")
        feedback_columns = [column[1] for column in cursor.fetchall()]
        if "poster_path" not in feedback_columns:
            try:
                cursor.execute("ALTER TABLE media_feedback ADD COLUMN poster_path TEXT")
            except Exception:
                pass
        conn.commit()


def get_user_request_meta(user_id: str):
    return system_store.fetch_one(
        "SELECT admin_disabled, expire_date, emby_pw_hash, req_free, req_free_count, points FROM users_meta WHERE user_id = ?",
        (user_id,),
    )


def get_user_status_meta(user_id: str):
    return system_store.fetch_one("SELECT admin_disabled, expire_date FROM users_meta WHERE user_id = ?", (user_id,))


def get_user_expire_date(user_id: str):
    return system_store.fetch_one("SELECT expire_date FROM users_meta WHERE user_id = ?", (user_id,))


def get_user_password_hash(user_id: str):
    return system_store.fetch_one("SELECT emby_pw_hash FROM users_meta WHERE user_id = ?", (user_id,))


def update_user_password_hash(user_id: str, password_hash: str) -> None:
    system_store.execute("UPDATE users_meta SET emby_pw_hash = ? WHERE user_id = ?", (password_hash, user_id))


def get_point_config_value(key: str):
    row = system_store.fetch_one("SELECT value FROM point_config WHERE key = ?", (key,))
    return row["value"] if row else None


def get_point_config_map(keys):
    if not keys:
        return {}
    placeholders = ",".join(["?" for _ in keys])
    rows = system_store.fetch_all(f"SELECT key, value FROM point_config WHERE key IN ({placeholders})", list(keys))
    return {row["key"]: row["value"] for row in rows}


def _get_int_config(config, key, default):
    try:
        return int(config.get(key, default))
    except Exception:
        return default


def submit_new_media_request(user_id, username, tmdb_id, media_type, title, year, poster_path, seasons):
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")

            config = get_point_config_map(["enable_req_cost", "req_cost", "req_cost_mode"])
            global_enable_cost = config.get("enable_req_cost") == "1"

            cursor.execute("SELECT req_free, req_free_count, points FROM users_meta WHERE user_id = ?", (user_id,))
            user_row = cursor.fetchone()
            user_req_free = user_row[0] if user_row else 0
            user_req_free_count = user_row[1] if user_row else -1

            need_cost = False
            if user_req_free == 1:
                need_cost = False
                if user_req_free_count == 0:
                    conn.rollback()
                    return {"ok": False, "message": "您的免费求片次数已用完，请联系管理员。"}
            elif user_req_free == 2:
                need_cost = True
            else:
                need_cost = global_enable_cost

            request_cost = 0
            current_points = 0
            if need_cost:
                base_cost = _get_int_config(config, "req_cost", 50)
                cost_mode = config.get("req_cost_mode") or "per_request"
                request_cost = base_cost * len(seasons) if cost_mode == "per_season" else base_cost

                cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,))
                points_row = cursor.fetchone()
                current_points = points_row[0] if points_row else 0
                if current_points < request_cost and request_cost > 0:
                    conn.rollback()
                    mode_hint = {"per_request": "每次", "per_season": "每季"}
                    count_hint = len(seasons) if cost_mode == "per_season" else 1
                    return {
                        "ok": False,
                        "message": f"积分不足！求片需消耗 {request_cost} 积分（{mode_hint.get(cost_mode, '单次')}{base_cost}积分×{count_hint}），当前仅有 {current_points} 积分。请前往首页签到。",
                    }

            for season in seasons:
                cursor.execute("SELECT status FROM media_requests WHERE tmdb_id = ? AND season = ?", (tmdb_id, season))
                existing = cursor.fetchone()
                if not existing:
                    cursor.execute(
                        "INSERT OR IGNORE INTO media_requests (tmdb_id, media_type, title, year, poster_path, status, season, request_type) VALUES (?, ?, ?, ?, ?, 0, ?, 'new')",
                        (tmdb_id, media_type, title, year, poster_path, season),
                    )
                    cursor.execute(
                        "INSERT OR IGNORE INTO request_users (tmdb_id, user_id, username, season) VALUES (?, ?, ?, ?)",
                        (tmdb_id, user_id, username, season),
                    )

            if need_cost and request_cost > 0:
                new_points = current_points - request_cost
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))
                season_info = f"({len(seasons)}季)" if media_type == "tv" and len(seasons) > 1 else ""
                cursor.execute(
                    "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                    (user_id, username, f"求片心愿: {title}{season_info}", -request_cost, new_points),
                )

            if user_req_free == 1 and user_req_free_count > 0:
                cursor.execute("UPDATE users_meta SET req_free_count = req_free_count - 1 WHERE user_id = ?", (user_id,))

            conn.commit()
            return {"ok": True}
        except Exception:
            conn.rollback()
            raise


def submit_single_media_request(
    user_id,
    username,
    tmdb_id,
    media_type,
    title,
    year,
    poster_path,
    season,
):
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")

            config = get_point_config_map(["enable_req_cost", "req_cost"])
            global_enable_cost = config.get("enable_req_cost") == "1"

            cursor.execute("SELECT req_free, req_free_count, points FROM users_meta WHERE user_id = ?", (user_id,))
            user_row = cursor.fetchone()
            user_req_free = user_row[0] if user_row else 0
            user_req_free_count = user_row[1] if user_row else -1

            need_cost = False
            if user_req_free == 1:
                need_cost = False
                if user_req_free_count == 0:
                    conn.rollback()
                    return {"ok": False, "message": "您的免费求片次数已用完，请联系管理员。"}
            elif user_req_free == 2:
                need_cost = True
            else:
                need_cost = global_enable_cost

            request_cost = 0
            current_points = user_row[2] if user_row else 0
            if need_cost:
                request_cost = _get_int_config(config, "req_cost", 50)
                if current_points < request_cost:
                    conn.rollback()
                    return {
                        "ok": False,
                        "message": f"积分不足！求片需消耗 {request_cost} 积分，当前仅有 {current_points} 积分。",
                    }

            cursor.execute("SELECT status FROM media_requests WHERE tmdb_id = ? AND season = ?", (tmdb_id, season))
            existing = cursor.fetchone()
            if existing:
                conn.rollback()
                status_map = {0: "处理中", 1: "下载中", 2: "已完成", 3: "已拒绝", 4: "待手动处理"}
                return {"ok": False, "message": f"该资源工单已存在，当前状态：{status_map.get(existing[0], '未知')}"}

            if need_cost and request_cost > 0:
                new_points = current_points - request_cost
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))
                cursor.execute(
                    "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                    (user_id, username, f"提交求片心愿: {title}", -request_cost, new_points),
                )

            if user_req_free == 1 and user_req_free_count > 0:
                cursor.execute("UPDATE users_meta SET req_free_count = req_free_count - 1 WHERE user_id = ?", (user_id,))

            cursor.execute(
                "INSERT OR IGNORE INTO media_requests (tmdb_id, media_type, title, year, poster_path, status, season) VALUES (?, ?, ?, ?, ?, 0, ?)",
                (tmdb_id, media_type, title, year, poster_path, season),
            )
            cursor.execute(
                "INSERT OR IGNORE INTO request_users (tmdb_id, user_id, username, season) VALUES (?, ?, ?, ?)",
                (tmdb_id, user_id, username, season),
            )
            conn.commit()
            return {
                "ok": True,
                "need_cost": need_cost,
                "request_cost": request_cost,
                "user_req_free": user_req_free,
                "user_req_free_count": user_req_free_count,
            }
        except Exception:
            conn.rollback()
            raise


def list_my_requests(user_id: str):
    return system_store.fetch_all(
        """
        SELECT m.tmdb_id, m.title, m.year, m.poster_path, m.status, m.season, m.media_type,
               r.requested_at, m.reject_reason, m.episodes, m.request_type
        FROM request_users r JOIN media_requests m
        ON r.tmdb_id = m.tmdb_id AND r.season = m.season
        WHERE r.user_id = ? ORDER BY r.requested_at DESC
        """,
        (user_id,),
    )


def list_user_recent_requests(user_id: str, limit: int = 10):
    return system_store.fetch_all(
        """
        SELECT mr.title, mr.year, mr.status, mr.season, mr.media_type
        FROM media_requests mr
        INNER JOIN request_users ru ON mr.tmdb_id = ru.tmdb_id AND mr.season = ru.season
        WHERE ru.user_id = ?
        ORDER BY mr.rowid DESC
        LIMIT ?
        """,
        (user_id, limit),
    )


def list_all_requests():
    return system_store.fetch_all(
        """
        SELECT m.tmdb_id, m.media_type, m.title, m.year, m.poster_path, m.status, m.season,
               m.created_at, COUNT(r.user_id) as cnt,
               GROUP_CONCAT(COALESCE(r.username, '系统用户'), ', ') as users, m.reject_reason,
               m.episodes, m.request_type, m.series_id
        FROM media_requests m
        LEFT JOIN request_users r ON m.tmdb_id = r.tmdb_id AND m.season = r.season
        GROUP BY m.tmdb_id, m.season
        ORDER BY m.status ASC, m.created_at DESC
        """
    )


def get_request_summary_by_tmdb(tmdb_id):
    return system_store.fetch_one("SELECT media_type, title FROM media_requests WHERE tmdb_id = ? LIMIT 1", (tmdb_id,))


def list_pending_requests_by_tmdb(tmdb_id):
    return system_store.fetch_all(
        "SELECT season, title, media_type, year FROM media_requests WHERE tmdb_id = ? AND status = 0",
        (tmdb_id,),
    )


def get_media_request(tmdb_id, season):
    return system_store.fetch_one("SELECT * FROM media_requests WHERE tmdb_id = ? AND season = ?", (tmdb_id, season))


def list_pending_sync_requests():
    return system_store.fetch_all(
        "SELECT tmdb_id, media_type, season, request_type, episodes FROM media_requests WHERE status IN (0, 1, 4, 7)"
    )


def mark_sync_request_finished(tmdb_id, season=None) -> None:
    if season is None:
        system_store.execute("UPDATE media_requests SET status = 2, updated_at = CURRENT_TIMESTAMP WHERE tmdb_id = ?", (tmdb_id,))
    else:
        system_store.execute(
            "UPDATE media_requests SET status = 2, updated_at = CURRENT_TIMESTAMP WHERE tmdb_id = ? AND season = ?",
            (tmdb_id, season),
        )


def update_media_request_status(tmdb_id, season, status, reject_reason=None) -> None:
    if reject_reason is None:
        system_store.execute("UPDATE media_requests SET status = ? WHERE tmdb_id = ? AND season = ?", (status, tmdb_id, season))
    else:
        system_store.execute(
            "UPDATE media_requests SET status = ?, reject_reason = ? WHERE tmdb_id = ? AND season = ?",
            (status, reject_reason, tmdb_id, season),
        )


def delete_media_request(tmdb_id, season) -> None:
    with system_store.connect() as conn:
        conn.execute("DELETE FROM media_requests WHERE tmdb_id = ? AND season = ?", (tmdb_id, season))
        conn.execute("DELETE FROM request_users WHERE tmdb_id = ? AND season = ?", (tmdb_id, season))
        conn.commit()


def finish_media_requests_for_item(tmdb_id, season=None):
    with system_store.connect() as conn:
        cursor = conn.cursor()
        if season is None:
            cursor.execute(
                "SELECT title, year, media_type, season FROM media_requests WHERE tmdb_id = ? AND status IN (0, 1, 4, 7)",
                (tmdb_id,),
            )
        else:
            cursor.execute(
                "SELECT title, year, media_type, season FROM media_requests WHERE tmdb_id = ? AND season = ? AND status IN (0, 1, 4, 7)",
                (tmdb_id, season),
            )
        requests_to_notify = [to_data_row(row) for row in cursor.fetchall()]

        users_to_notify = []
        for request_row in requests_to_notify:
            cursor.execute(
                "SELECT user_id, username FROM request_users WHERE tmdb_id = ? AND season = ?",
                (tmdb_id, request_row["season"]),
            )
            users_to_notify.extend(to_data_row(row) for row in cursor.fetchall())

        if season is None:
            cursor.execute(
                "UPDATE media_requests SET status = 2, updated_at = CURRENT_TIMESTAMP WHERE tmdb_id = ? AND status IN (0, 1, 4, 7)",
                (tmdb_id,),
            )
        else:
            cursor.execute(
                "UPDATE media_requests SET status = 2, updated_at = CURRENT_TIMESTAMP WHERE tmdb_id = ? AND season = ? AND status IN (0, 1, 4, 7)",
                (tmdb_id, season),
            )
        conn.commit()

    return requests_to_notify, users_to_notify


def list_request_status_notify_items(items):
    notify_items = []
    user_ids = []
    with system_store.connect() as conn:
        cursor = conn.cursor()
        for item in items:
            tmdb_id = item["tmdb_id"]
            season = item["season"]
            cursor.execute(
                "SELECT title, year, media_type, season, episodes, poster_path FROM media_requests WHERE tmdb_id = ? AND season = ?",
                (tmdb_id, season),
            )
            request_row = to_data_row(cursor.fetchone())
            cursor.execute("SELECT user_id, username FROM request_users WHERE tmdb_id = ? AND season = ?", (tmdb_id, season))
            users = [to_data_row(row) for row in cursor.fetchall()]
            if request_row and users:
                notify_items.append({"tmdb_id": tmdb_id, "season": season, "request": request_row, "users": users})
                user_ids.extend([user["user_id"] for user in users])
    return notify_items, user_ids


def list_tg_bindings(user_ids):
    if not user_ids:
        return {}
    unique_ids = list(dict.fromkeys(user_ids))
    placeholders = ",".join(["?"] * len(unique_ids))
    rows = system_store.fetch_all(
        f"SELECT emby_user_id, tg_user_id FROM tg_user_bindings WHERE emby_user_id IN ({placeholders})",
        unique_ids,
    )
    return {row["emby_user_id"]: row["tg_user_id"] for row in rows}


def get_pending_notify_data():
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM media_requests WHERE status = 0")
        request_count = cursor.fetchone()["cnt"]
        cursor.execute(
            "SELECT m.tmdb_id, m.media_type, m.title, m.poster_path, m.season, datetime(m.created_at, 'localtime') as created_at, GROUP_CONCAT(COALESCE(r.username, '未知用户'), ', ') as users FROM media_requests m LEFT JOIN request_users r ON m.tmdb_id = r.tmdb_id AND m.season = r.season WHERE m.status = 0 GROUP BY m.tmdb_id, m.season ORDER BY m.created_at DESC LIMIT 5"
        )
        request_rows = [to_data_row(row) for row in cursor.fetchall()]
        cursor.execute("SELECT COUNT(*) as cnt FROM media_feedback WHERE status = 0")
        feedback_count = cursor.fetchone()["cnt"]
        cursor.execute(
            """
            SELECT f.id, f.item_name, f.username, f.issue_type, datetime(f.created_at, 'localtime') as created_at,
                   COALESCE(
                       NULLIF(f.poster_path, ''),
                       (SELECT poster_path FROM media_requests m WHERE m.title = f.item_name LIMIT 1),
                       (SELECT poster_path FROM media_requests m WHERE f.item_name LIKE m.title || '%' LIMIT 1)
                   ) as poster
            FROM media_feedback f
            WHERE f.status = 0 ORDER BY f.created_at DESC LIMIT 5
            """
        )
        feedback_rows = [to_data_row(row) for row in cursor.fetchall()]
    return request_count, request_rows, feedback_count, feedback_rows


def find_poster_for_feedback(item_name: str):
    return system_store.fetch_one("SELECT poster_path FROM media_requests WHERE ? LIKE title || '%' LIMIT 1", (item_name,))


def create_media_feedback(item_name, user_id, username, issue_type, description, poster_path) -> int:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO media_feedback (item_name, user_id, username, issue_type, description, poster_path) VALUES (?, ?, ?, ?, ?, ?)",
            (item_name, user_id, username, issue_type, description, poster_path),
        )
        conn.commit()
        return cursor.lastrowid


def list_my_feedback(user_id: str):
    return system_store.fetch_all(
        "SELECT id, item_name, issue_type, description, status, datetime(created_at, 'localtime') as created_at FROM media_feedback WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )


def list_all_feedback():
    return system_store.fetch_all(
        "SELECT id, item_name, username, issue_type, description, status, datetime(created_at, 'localtime') as created_at FROM media_feedback ORDER BY status ASC, created_at DESC"
    )


def update_feedback_status(feedback_id: int, status: int) -> None:
    if status == -1:
        system_store.execute("DELETE FROM media_feedback WHERE id = ?", (feedback_id,))
    else:
        system_store.execute("UPDATE media_feedback SET status = ? WHERE id = ?", (status, feedback_id))


def update_feedback_status_batch(feedback_ids, status: int) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        for feedback_id in feedback_ids:
            if status == -1:
                cursor.execute("DELETE FROM media_feedback WHERE id = ?", (feedback_id,))
            else:
                cursor.execute("UPDATE media_feedback SET status = ? WHERE id = ?", (status, feedback_id))
        conn.commit()


def get_user_series_db_context():
    cache_row = system_store.fetch_one("SELECT result_json, updated_at FROM gap_scan_cache WHERE id = 1")
    interval_value = get_gap_config_value("cache_interval_hours")
    interval_hours = int(interval_value) if interval_value else 6
    update_requests = {}
    for row in system_store.fetch_all("SELECT tmdb_id, season, episodes, status FROM media_requests WHERE request_type = 'update'"):
        key = f"{row['tmdb_id']}_{row['season']}"
        update_requests[key] = {"episodes": row["episodes"] or "", "status": row["status"]}
    return cache_row, interval_hours, update_requests


def get_gap_config_value(key: str):
    row = system_store.fetch_one("SELECT value FROM gap_config WHERE key = ?", (key,))
    return row["value"] if row else None


def get_update_cost_config():
    config = get_point_config_map(["enable_update_cost", "update_cost", "update_cost_mode"])
    return {
        "enabled": config.get("enable_update_cost") == "1",
        "cost": _get_int_config(config, "update_cost", 20),
        "mode": config.get("update_cost_mode") or "per_series",
    }


_STATUS_TEXT = {0: "待审批", 1: "下载中", 2: "已完成", 3: "已拒绝", 4: "手动接单", 7: "待入库"}


def _parse_episode_list(episodes_text):
    return [int(episode) for episode in (episodes_text or "").split(",") if episode.strip().isdigit()]


def submit_update_request_record(user_id, username, series_id, tmdb_id, title, year, poster_path, season, episodes):
    episodes_str = ",".join(str(episode) for episode in sorted(episodes))
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")

            cursor.execute("SELECT COUNT(*) FROM media_requests WHERE tmdb_id = ? AND request_type = 'update'", (tmdb_id,))
            existing_update_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM media_requests WHERE tmdb_id = ? AND season = ? AND request_type = 'update'",
                (tmdb_id, season),
            )
            existing_season_update_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT tmdb_id, season, status, episodes, request_type FROM media_requests WHERE tmdb_id = ? AND season = ?",
                (tmdb_id, season),
            )
            existing = cursor.fetchone()

            if existing:
                existing_status = existing[2]
                existing_episodes = existing[3] or ""
                existing_request_type = existing[4] or "new"
                if existing_request_type == "new":
                    if existing_status in (2, 3):
                        cursor.execute(
                            "UPDATE media_requests SET request_type = 'update', status = 0, episodes = ?, reject_reason = NULL WHERE tmdb_id = ? AND season = ?",
                            (episodes_str, tmdb_id, season),
                        )
                        cursor.execute(
                            "INSERT OR IGNORE INTO request_users (tmdb_id, user_id, username, season) VALUES (?, ?, ?, ?)",
                            (tmdb_id, user_id, username, season),
                        )
                    else:
                        conn.rollback()
                        status_text = _STATUS_TEXT.get(existing_status, str(existing_status))
                        return {
                            "ok": False,
                            "message": f"该剧第{season}季正在求片中（{status_text}），请等待完成后再追新，或联系管理员取消求片请求",
                        }
                elif existing_request_type == "update":
                    existing_list = _parse_episode_list(existing_episodes)
                    if existing_status in (0, 1, 4, 7):
                        duplicate_eps = [episode for episode in episodes if episode in existing_list]
                        if duplicate_eps:
                            conn.rollback()
                            return {"ok": False, "message": f"以下集数已在追更列表中：E{','.join(str(e) for e in duplicate_eps)}"}
                        merged = sorted(set(existing_list + episodes))
                        episodes_str = ",".join(str(episode) for episode in merged)
                        cursor.execute("UPDATE media_requests SET episodes = ? WHERE tmdb_id = ? AND season = ?", (episodes_str, tmdb_id, season))
                        cursor.execute(
                            "INSERT OR IGNORE INTO request_users (tmdb_id, user_id, username, season) VALUES (?, ?, ?, ?)",
                            (tmdb_id, user_id, username, season),
                        )
                    elif existing_status == 2:
                        new_episodes = [episode for episode in episodes if episode not in existing_list]
                        if not new_episodes:
                            conn.rollback()
                            return {"ok": False, "message": "这些集数已经入库了"}
                        merged = sorted(set(existing_list + new_episodes))
                        episodes_str = ",".join(str(episode) for episode in merged)
                        cursor.execute(
                            "UPDATE media_requests SET status = 0, episodes = ?, reject_reason = NULL WHERE tmdb_id = ? AND season = ?",
                            (episodes_str, tmdb_id, season),
                        )
                        cursor.execute(
                            "INSERT OR IGNORE INTO request_users (tmdb_id, user_id, username, season) VALUES (?, ?, ?, ?)",
                            (tmdb_id, user_id, username, season),
                        )
                    elif existing_status == 3:
                        cursor.execute(
                            "UPDATE media_requests SET status = 0, episodes = ?, reject_reason = NULL WHERE tmdb_id = ? AND season = ?",
                            (episodes_str, tmdb_id, season),
                        )
                        cursor.execute(
                            "INSERT OR IGNORE INTO request_users (tmdb_id, user_id, username, season) VALUES (?, ?, ?, ?)",
                            (tmdb_id, user_id, username, season),
                        )
                    else:
                        cursor.execute(
                            "UPDATE media_requests SET status = 0, episodes = ?, request_type = 'update' WHERE tmdb_id = ? AND season = ?",
                            (episodes_str, tmdb_id, season),
                        )
                        cursor.execute(
                            "INSERT OR IGNORE INTO request_users (tmdb_id, user_id, username, season) VALUES (?, ?, ?, ?)",
                            (tmdb_id, user_id, username, season),
                        )
            else:
                cursor.execute(
                    """
                    INSERT INTO media_requests
                    (tmdb_id, media_type, title, year, poster_path, status, season, episodes, request_type, series_id)
                    VALUES (?, 'tv', ?, ?, ?, 0, ?, ?, 'update', ?)
                    """,
                    (tmdb_id, title, year, poster_path, season, episodes_str, series_id),
                )
                cursor.execute(
                    "INSERT OR IGNORE INTO request_users (tmdb_id, user_id, username, season) VALUES (?, ?, ?, ?)",
                    (tmdb_id, user_id, username, season),
                )

            config = get_update_cost_config()
            update_cost = 0
            current_points = 0
            cost_mode = config["mode"]
            base_cost = config["cost"]
            if config["enabled"]:
                if cost_mode in ("per_series", "per_season"):
                    update_cost = base_cost
                elif cost_mode == "per_episode":
                    if existing and existing[4] == "update":
                        existing_eps = _parse_episode_list(existing[3] or "")
                        update_cost = base_cost * len([episode for episode in episodes if episode not in existing_eps])
                    else:
                        update_cost = base_cost * len(episodes)
                else:
                    update_cost = base_cost

                cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,))
                points_row = cursor.fetchone()
                current_points = points_row[0] if points_row else 0
                if current_points < update_cost and update_cost > 0:
                    conn.rollback()
                    mode_hint = {"per_series": "每剧", "per_season": "每季", "per_episode": "每集"}
                    count_hint = len(episodes) if cost_mode == "per_episode" else 1
                    return {
                        "ok": False,
                        "message": f"积分不足！追新需消耗 {update_cost} 积分（{mode_hint.get(cost_mode, '单次')}{base_cost}积分×{count_hint}），当前仅有 {current_points} 积分",
                    }

            if config["enabled"] and update_cost > 0:
                new_points = current_points - update_cost
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))
                cursor.execute(
                    "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                    (user_id, username, f"追新请求: {title} S{season}E{episodes_str}", -update_cost, new_points),
                )

            conn.commit()
            return {
                "ok": True,
                "episodes_str": episodes_str,
                "cost_enabled": config["enabled"],
                "cost": update_cost,
                "existing_update_count": existing_update_count,
                "existing_season_update_count": existing_season_update_count,
            }
        except Exception:
            conn.rollback()
            raise


def submit_batch_update_request_records(user_id, username, requests_list, series_name, fallback_tmdb_id):
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            config = get_update_cost_config()
            total_seasons = len(requests_list)
            total_episodes = sum(len(request.get("episodes", [])) for request in requests_list)
            total_cost = 0
            if config["mode"] == "per_series":
                total_cost = config["cost"]
            elif config["mode"] == "per_season":
                total_cost = config["cost"] * total_seasons
            elif config["mode"] == "per_episode":
                total_cost = config["cost"] * total_episodes

            current_points = 0
            if config["enabled"] and total_cost > 0:
                cursor.execute("SELECT points FROM users_meta WHERE user_id = ?", (user_id,))
                points_row = cursor.fetchone()
                current_points = points_row[0] if points_row else 0
                if current_points < total_cost:
                    conn.rollback()
                    return {"ok": False, "message": f"积分不足！需消耗 {total_cost} 积分，当前仅有 {current_points} 积分"}

            for request in requests_list:
                tmdb_id = int(request.get("tmdb_id") or fallback_tmdb_id)
                season = int(request.get("season") or 0)
                episodes = [int(episode) for episode in request.get("episodes", []) if int(episode) > 0]
                title = request.get("title", series_name)
                year = request.get("year", "")
                poster_path = request.get("poster_path", "")
                series_id = request.get("series_id", "")
                if not tmdb_id or not season or not episodes:
                    continue
                episodes_str = ",".join(str(episode) for episode in sorted(episodes))
                cursor.execute(
                    "SELECT tmdb_id, season, status, episodes, request_type FROM media_requests WHERE tmdb_id = ? AND season = ?",
                    (tmdb_id, season),
                )
                existing = cursor.fetchone()
                if existing:
                    existing_status = existing[2]
                    existing_episodes = existing[3] or ""
                    existing_request_type = existing[4] or "new"
                    if existing_request_type == "update" and existing_status in (0, 1, 4, 7):
                        existing_list = _parse_episode_list(existing_episodes)
                        new_episodes = [episode for episode in episodes if episode not in existing_list]
                        if new_episodes:
                            merged = sorted(set(existing_list + new_episodes))
                            episodes_str = ",".join(str(episode) for episode in merged)
                            cursor.execute("UPDATE media_requests SET episodes = ? WHERE tmdb_id = ? AND season = ?", (episodes_str, tmdb_id, season))
                            cursor.execute(
                                "INSERT OR IGNORE INTO request_users (tmdb_id, user_id, username, season) VALUES (?, ?, ?, ?)",
                                (tmdb_id, user_id, username, season),
                            )
                    elif existing_request_type == "new" and existing_status in (2, 3):
                        cursor.execute(
                            "UPDATE media_requests SET request_type = 'update', status = 0, episodes = ?, reject_reason = NULL WHERE tmdb_id = ? AND season = ?",
                            (episodes_str, tmdb_id, season),
                        )
                        cursor.execute(
                            "INSERT OR IGNORE INTO request_users (tmdb_id, user_id, username, season) VALUES (?, ?, ?, ?)",
                            (tmdb_id, user_id, username, season),
                        )
                else:
                    cursor.execute(
                        """
                        INSERT INTO media_requests
                        (tmdb_id, media_type, title, year, poster_path, status, season, episodes, request_type, series_id)
                        VALUES (?, 'tv', ?, ?, ?, 0, ?, ?, 'update', ?)
                        """,
                        (tmdb_id, title, year, poster_path, season, episodes_str, series_id),
                    )
                    cursor.execute(
                        "INSERT OR IGNORE INTO request_users (tmdb_id, user_id, username, season) VALUES (?, ?, ?, ?)",
                        (tmdb_id, user_id, username, season),
                    )

            if config["enabled"] and total_cost > 0:
                new_points = current_points - total_cost
                cursor.execute("UPDATE users_meta SET points = ? WHERE user_id = ?", (new_points, user_id))
                cursor.execute(
                    "INSERT INTO point_logs (user_id, username, action, amount, balance) VALUES (?, ?, ?, ?, ?)",
                    (user_id, username, f"批量追新: {series_name} ({total_seasons}季, {total_episodes}集)", -total_cost, new_points),
                )

            conn.commit()
            return {"ok": True, "total_cost": total_cost, "total_seasons": total_seasons, "total_episodes": total_episodes, "cost_mode": config["mode"]}
        except Exception:
            conn.rollback()
            raise


def get_update_request_search_info(tmdb_id, season):
    return system_store.fetch_one(
        "SELECT title, series_id FROM media_requests WHERE tmdb_id = ? AND season = ? AND request_type = 'update'",
        (tmdb_id, season),
    )


def restore_invitation_code(code: str) -> None:
    system_store.execute(
        "UPDATE invitations SET used_count = MAX(used_count - 1, 0), used_by = NULL, used_at = NULL WHERE code = ?",
        (code,),
    )


def claim_registration_invitation(code: str, used_by: str):
    with system_store.connect() as conn:
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cursor.execute(
                """
                UPDATE invitations
                SET used_count = used_count + 1,
                    used_at = datetime('now','localtime'),
                    used_by = ?
                WHERE code = ? AND status != 1 AND used_count < max_uses
                AND (type IS NULL OR type = 'register')
                """,
                (used_by, code),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                cursor.execute("SELECT 1 FROM invitations WHERE code = ?", (code,))
                exists = cursor.fetchone()
                if not exists:
                    return None, "邀请码无效"
                return None, "邀请码已失效或已达到使用上限"
            cursor.execute("SELECT * FROM invitations WHERE code = ?", (code,))
            invite = to_data_row(cursor.fetchone())
            used_count = invite["used_count"] if invite["used_count"] else 0
            max_uses = invite["max_uses"] if invite["max_uses"] else 1
            if used_count >= max_uses:
                cursor.execute("UPDATE invitations SET status = 1 WHERE code = ?", (code,))
            conn.commit()
            return invite, None
        except Exception:
            conn.rollback()
            raise


def save_registered_user_meta(user_id, expire_date, allow_routes, block_routes, req_free, req_free_count, admin_enabled_folders) -> None:
    with system_store.connect() as conn:
        cursor = conn.cursor()
        ensure_registered_table(cursor, "users_meta", {"admin_enabled_folders"})
        admin_folders = ",".join(admin_enabled_folders) if admin_enabled_folders else None
        cursor.execute(
            """
            INSERT OR REPLACE INTO users_meta
            (user_id, expire_date, allow_routes, block_routes, req_free, req_free_count, admin_enabled_folders, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
            """,
            (user_id, expire_date, allow_routes, block_routes, req_free, req_free_count, admin_folders),
        )
        conn.commit()


def decode_gap_cache(cache_row):
    if cache_row and cache_row["result_json"]:
        try:
            return json.loads(cache_row["result_json"])
        except Exception:
            return []
    return []
