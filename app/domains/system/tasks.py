import asyncio
import datetime
from fastapi import APIRouter, Request
from app.domains.users.auth import is_admin_user  # 🔒 引入管理员权限检查
from pydantic import BaseModel
from app.infra.db.notification_dao import add_system_notification
from app.domains.system.task_dao import (
    delete_task_translation,
    ensure_task_config_defaults,
    is_task_notify_enabled,
    list_task_translations,
    save_task_translation,
    set_task_notify_enabled,
)
from app.infra.clients.media_server_client import media_api
from app.domains.notifications.bot_service import bot
from app.core.security_utils import safe_error_message

router = APIRouter()

# ==========================================
# 1. 基础字典 (涵盖常见官方任务与百大主流插件)
# ==========================================
COMMON_TASK_DICT = {
    "Scan media library": "扫描媒体库",
    "Refresh Guide": "刷新电视指南",
    "Refresh channels": "刷新直播频道",
    "Clean up collections and playlists": "清理合集与播放列表",
    "Refresh people": "刷新演员与人物信息",
    "Refresh network shows": "刷新网络剧集",
    "Clean up image cache": "清理图像缓存",
    "Download missing subtitles": "下载缺失的字幕",
    "Extract chapter images": "提取视频章节图片",
    "Refresh local IP addresses": "刷新本地 IP 地址",
    "Check for application updates": "检查系统更新",
    "Check for plugin updates": "检查插件更新",
    "Optimize database": "优化数据库结构",
    "Vacuum database": "压缩与清理数据库 (Vacuum)",
    "Remove old watch history": "移除陈旧的播放历史",
    "Sync Playstate": "同步播放状态",
    "Update Plugins": "自动更新插件",
    "Update server": "自动更新服务器",
    "Cache images": "缓存图像",
    "Backup database": "备份服务器数据库",
    "Auto Organize": "自动整理媒体",
    "Generate Intro Video": "生成片头视频",
    "Rotate log file": "轮转并清理日志文件",
    "Clean up sync directories": "清理同步目录",
    "Convert media": "转换媒体格式",
    "Refresh library metadata": "刷新媒体库元数据",
    "Scan local network": "扫描本地局域网设备",
    "Download missing plugin updates": "下载缺失的插件更新",
    "Remove old sync jobs": "移除陈旧的同步任务",
    
    "Scrape Jav": "JavScraper 搜刮器同步",
    "Update JavScraper Index": "更新 JavScraper 索引",
    "MetaTube: Update Subscriptions": "MetaTube: 更新订阅",
    "MetaTube: Auto Update Metadata": "MetaTube: 自动更新元数据",
    "TMDb: Refresh metadata": "TMDb: 刷新元数据",
    "TheMovieDb: Refresh metadata": "TheMovieDb: 刷新元数据",
    "OMDb: Refresh metadata": "OMDb: 刷新元数据",
    "TVDb: Refresh metadata": "TVDb: 刷新元数据",
    "Douban: Refresh metadata": "豆瓣(Douban): 刷新元数据",
    "Bgm.tv: Refresh metadata": "Bgm.tv: 刷新动漫元数据",
    "Bangumi: Refresh metadata": "Bangumi: 刷新动漫元数据",
    "AniDB: Refresh metadata": "AniDB: 刷新动漫元数据",
    "Kitsu: Refresh metadata": "Kitsu: 刷新动漫元数据",
    
    "Open Subtitles: Download missing subtitles": "Open Subtitles: 下载缺失字幕",
    "Subscene: Download missing subtitles": "Subscene: 下载缺失字幕",
    "Shooter: Download missing subtitles": "伪射手(Shooter): 下载缺失字幕",
    "Thunder: Download missing subtitles": "迅雷(Thunder): 下载缺失字幕",
    "Fanart.tv: Download missing images": "Fanart.tv: 下载缺失的海报与艺术图",
    "Screen Grabber: Extract chapter images": "截屏器: 提取视频章节预览图",
    
    "Trakt.tv: Sync Library": "Trakt.tv: 同步媒体库",
    "Trakt.tv: Import Playstates": "Trakt.tv: 导入播放状态",
    "Trakt: Sync Library": "Trakt: 同步媒体库",
    "Trakt: Import Playstates": "Trakt: 导入播放状态",
    "Auto Box Sets: Create Collections": "Auto Box Sets: 自动创建电影合集",
    "Intro Skipper: Analyze Audio": "跳过片头(Intro Skipper): 分析音频指纹",
    "Intro Skipper: Analyze Video": "跳过片头(Intro Skipper): 分析视频画面",
    "Theme Songs: Download theme songs": "主题曲: 下载剧集主题曲",
    "Theme Videos: Download theme videos": "主题视频: 下载剧集主题背景视频",
    
    "Playback Reporting: Backup database": "播放统计: 备份统计数据库",
    "Playback Reporting: Aggregate Data": "播放统计: 聚合计算历史数据",
    "EmbyStat: Refresh data": "EmbyStat: 刷新统计数据",
    "Statistics: Calculate statistics": "数据看板: 计算全站数据",
    "Statistics: Clean up old data": "数据看板: 清理过期数据",
    "Webhooks: Send test webhook": "Webhooks: 发送测试通知",
    "Slack: Send test notification": "Slack: 发送测试通知",
    "Telegram: Send test notification": "Telegram: 发送测试通知",
    "Discord: Send test notification": "Discord: 发送测试通知",
    
    "M3U: Refresh guide": "M3U: 刷新直播节目单",
    "XmlTV: Refresh guide": "XmlTV: 刷新直播节目单",
    "HDHomeRun: Refresh guide": "HDHomeRun: 刷新直播节目单"
}

# ==========================================
# 🔥 新增：任务通知配置模块
# ==========================================
# 表结构由 db_schemas.py 统一管理，初始化默认值在这里

def init_task_config_defaults():
    """初始化任务配置默认值"""
    try:
        ensure_task_config_defaults()
    except Exception as e: pass

init_task_config_defaults()

class TaskConfigModel(BaseModel):
    enable_notify: bool

@router.get("/api/tasks/config")
async def get_task_config(request: Request):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        return {"status": "success", "enable_notify": is_task_notify_enabled()}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/tasks/config")
async def set_task_config(data: TaskConfigModel, request: Request):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        set_task_notify_enabled(data.enable_notify)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}


# ==========================================
# 🔥 优化：带开关拦截的后台守护进程
# ==========================================
_task_last_end_times = {}
_poller_initialized = False

def fetch_emby_tasks():
    try: return media_api.get("/ScheduledTasks", timeout=5).json()
    except: return None

async def poll_emby_tasks():
    global _task_last_end_times, _poller_initialized
    while True:
        try:
            tasks = await asyncio.to_thread(fetch_emby_tasks)
            if tasks:
                custom_trans_rows = list_task_translations()
                custom_dict = {r['original_name']: r['translated_name'] for r in custom_trans_rows} if custom_trans_rows else {}

                for t in tasks:
                    tid = t.get('Id')
                    orig_name = t.get('Name', '')
                    display_name = custom_dict.get(orig_name, COMMON_TASK_DICT.get(orig_name, orig_name))
                    
                    last_result = t.get("LastExecutionResult")
                    if last_result:
                        end_time = last_result.get("EndTimeUtc")
                        status = last_result.get("Status", "Unknown")
                        
                        if _poller_initialized and end_time:
                            prev_end = _task_last_end_times.get(tid)
                            if prev_end and end_time != prev_end:
                                
                                # 🔥 检查是否开启了推送开关
                                notify_enabled = True
                                try:
                                    notify_enabled = is_task_notify_enabled()
                                except Exception: pass

                                if notify_enabled:
                                    now_str = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
                                    if status == "Completed":
                                        try: add_system_notification("system", f"任务完成: {display_name}", f"Emby 后台作业正常执行完毕", "/tasks")
                                        except Exception: pass
                                        try: bot.send_message("sys_notify", f"✅ <b>任务执行完成</b>\n\n📌 <b>任务</b>: {display_name}\n⏱️ <b>时间</b>: {now_str}\n📊 <b>状态</b>: 成功", platform="all")
                                        except Exception: pass
                                    elif status == "Failed":
                                        try: add_system_notification("system", f"任务失败: {display_name}", f"Emby 后台作业执行异常，请检查", "/tasks")
                                        except Exception: pass
                                        try: bot.send_message("sys_notify", f"❌ <b>任务执行失败</b>\n\n📌 <b>任务</b>: {display_name}\n⏱️ <b>时间</b>: {now_str}\n⚠️ <b>警告</b>: 运行异常，请前往后台检查 Emby 日志", platform="all")
                                        except Exception: pass
                        
                        if end_time:
                            _task_last_end_times[tid] = end_time
                            
                _poller_initialized = True
        except Exception as e: pass
        await asyncio.sleep(5)

@router.on_event("startup")
async def start_task_poller():
    asyncio.create_task(poll_emby_tasks())


# ==========================================
# 2. 初始化自定义别名表 (已迁移到 database.py 统一创建)
# ==========================================
class TranslationModel(BaseModel):
    original_name: str
    translated_name: str

@router.post("/api/tasks/translate")
async def translate_task(data: TranslationModel, request: Request):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    orig = data.original_name.strip()
    trans = data.translated_name.strip()
    if not orig: return {"status": "error", "message": "原名不能为空"}
    
    try:
        if trans:
            save_task_translation(orig, trans)
        else:
            delete_task_translation(orig)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

# ==========================================
# 3. 核心 API：获取并应用混合翻译
# ==========================================
@router.get("/api/tasks")
async def get_tasks(request: Request):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    
    try:
        res = media_api.get("/ScheduledTasks", timeout=5)
        tasks = res.json()
        
        custom_trans_rows = list_task_translations()
        custom_dict = {r['original_name']: r['translated_name'] for r in custom_trans_rows} if custom_trans_rows else {}
        
        groups = {}
        for t in tasks:
            cat = t.get('Category', '未分类')
            orig_name = t.get('Name', '')
            
            t['OriginalName'] = orig_name 
            
            if orig_name in custom_dict: t['Name'] = custom_dict[orig_name]
            elif orig_name in COMMON_TASK_DICT: t['Name'] = COMMON_TASK_DICT[orig_name]
                
            if cat not in groups: groups[cat] = []
            groups[cat].append(t)
            
        result = [{"title": k, "tasks": v} for k, v in groups.items()]
        
        cat_trans = {
            "Library": "媒体库扫描", "Application": "系统与应用",
            "Maintenance": "日常维护", "Live TV": "电视直播",
            "Sync": "状态同步", "Plugins": "插件自动化"
        }
        for r in result:
            if r["title"] in cat_trans: r["title"] = cat_trans[r["title"]]
            
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/tasks/{task_id}/start")
async def start_task(task_id: str, request: Request):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        media_api.post(f"/ScheduledTasks/Running/{task_id}", timeout=5)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}

@router.post("/api/tasks/{task_id}/stop")
async def stop_task(task_id: str, request: Request):
    if not is_admin_user(request): return {"status": "error", "message": "需要管理员权限"}
    try:
        media_api.delete(f"/ScheduledTasks/Running/{task_id}", timeout=5)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": safe_error_message(e)}
