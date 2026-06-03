from app.infra.clients.media_server_client import media_api
from app.infra.db.playback_store import playback_store


_media_api_provider = lambda: media_api
_playback_store_provider = lambda: playback_store


def set_dependency_providers(
    *,
    media_api_provider=None,
    playback_store_provider=None,
):
    global _media_api_provider
    global _playback_store_provider

    if media_api_provider is not None:
        _media_api_provider = media_api_provider
    if playback_store_provider is not None:
        _playback_store_provider = playback_store_provider


def cmd_now(bot, cid, platform):
    try:
        res = _media_api_provider().get("/Sessions", timeout=5)
        sessions = [s for s in res.json() if s.get("NowPlayingItem")]
        if not sessions:
            return bot.send_message(cid, "🟢 当前无人在看", platform=platform)

        msg = f"🟢 <b>当前正在播放 ({len(sessions)} 人)</b>\n\n"
        for s in sessions:
            item = s.get("NowPlayingItem", {})
            title = item.get("Name", "未知")
            if item.get("Type") == "Episode" and item.get("SeriesName"):
                title = f"《{item.get('SeriesName')}》 {title}"
            elif item.get("Type") == "Movie":
                title = f"《{title}》"

            client = s.get("Client", "未知端")
            username = s.get("UserName", "未知用户")

            play_state = s.get("PlayState", {})
            pos_ticks = play_state.get("PositionTicks", 0)
            run_ticks = item.get("RunTimeTicks", 1) or 1
            pct = int((pos_ticks / run_ticks) * 100)
            pct = min(max(pct, 0), 100)

            filled = int(pct / 10)
            bar = "█" * filled + "⚪️" * (10 - filled)

            msg += f"👤 <b>{username}</b> ({client})\n📺 {title}\n⏳ <code>[{bar}] {pct}%</code>\n\n"
        bot.send_message(cid, msg.strip(), platform=platform)
    except Exception:
        bot.send_message(cid, "❌ 连接失败", platform=platform)


def cmd_recent(bot, cid, platform):
    try:
        rows = _playback_store_provider().query("SELECT UserId, ItemName, DateCreated FROM PlaybackActivity ORDER BY DateCreated DESC LIMIT 10")
        if not rows:
            return bot.send_message(cid, "📭 无记录", platform=platform)

        msg = "📜 <b>最近播放记录 (Top 10)</b>\n\n"
        for r in rows:
            date = r["DateCreated"][5:16].replace("T", " ")
            name = bot._get_username(r["UserId"])
            item_name = r["ItemName"].replace(" - ", " ")
            msg += f"▫️ <code>{date}</code> | 👤 <b>{name}</b> > {item_name}\n"
        bot.send_message(cid, msg.strip(), platform=platform)
    except Exception:
        bot.send_message(cid, "❌ 查询失败", platform=platform)
