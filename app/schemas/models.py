from pydantic import BaseModel
from typing import Optional, List

class LoginModel(BaseModel):
    username: str
    password: str

class SettingsModel(BaseModel):
    emby_host: str
    emby_api_key: str
    tmdb_api_key: Optional[str] = ""
    proxy_url: Optional[str] = ""
    webhook_token: Optional[str] = ""
    hidden_users: List[str] = []
    emby_public_url: Optional[str] = ""  
    welcome_message: Optional[str] = ""  
    client_download_url: Optional[str] = ""
    moviepilot_url: Optional[str] = ""
    moviepilot_token: Optional[str] = ""
    pulse_url: Optional[str] = ""
    user_portal_url: Optional[str] = ""
    # 🔥 注册链接重定向到用户社区
    register_redirect_to_community: Optional[str] = "false"
    # 🔥 新增：双引擎模式开关
    playback_data_mode: Optional[str] = "sqlite"
    server_type: str = "emby"
    notify_user_login: bool = False     # 🔥 补上这行
    notify_item_deleted: bool = False   # 🔥 补上这行
# 🔥 新增风控全局字段
    enable_risk_control: Optional[bool] = False
    default_max_concurrent: Optional[int] = 2
    # 天气配置
    weather_source: Optional[str] = "wttr"  # wttr / qweather / amap
    weather_qweather_key: Optional[str] = ""
    weather_qweather_host: Optional[str] = ""  # 和风天气独立 API Host
    weather_amap_key: Optional[str] = ""

class BotSettingsModel(BaseModel):
    tg_bot_token: str
    tg_chat_id: str
    enable_bot: bool
    enable_notify: bool
    enable_library_notify: Optional[bool] = False

    wecom_corpid: Optional[str] = ""
    wecom_corpsecret: Optional[str] = ""
    wecom_agentid: Optional[str] = ""
    wecom_touser: Optional[str] = "@all"
    wecom_proxy_url: Optional[str] = "https://qyapi.weixin.qq.com"
    wecom_token: Optional[str] = ""
    wecom_aeskey: Optional[str] = ""

    # 🤖 Pro: 用户机器人
    tg_user_bot_token: Optional[str] = ""
    user_bot_open_reg: Optional[bool] = False
    user_bot_open_reg_notify_user: Optional[bool] = False  # 通知用户机器人私聊
    user_bot_open_reg_notify_group: Optional[bool] = False  # 通知群聊
    user_bot_max_reg: Optional[int] = 0
    user_bot_reg_days: Optional[int] = 30
    user_bot_template_user: Optional[str] = ""
    user_bot_portal_url: Optional[str] = ""
    # 开放注册线路设置
    user_bot_route_mode: Optional[str] = "block"  # 'block' 或 'allow'
    user_bot_allow_routes: Optional[str] = ""
    user_bot_block_routes: Optional[str] = ""
    # 🎯 开放注册名额模式
    user_bot_reg_quota_mode: Optional[str] = "total"  # 'batch' 批次模式 / 'total' 总人数模式
    user_bot_reg_quota: Optional[int] = 0  # 名额上限
    user_bot_reg_batch_used: Optional[int] = 0  # 批次模式已使用数量
    
    # 🎯 群聊设置
    user_bot_group_enabled: Optional[bool] = False
    user_bot_allowed_groups: Optional[str] = ""  # 允许的群ID，换行分隔
    user_bot_group_commands: Optional[str] = "checkin,help,points,rank,transfer,rob,hb,grab,pk,lottery,scratch"  # 群内允许的指令，逗号分隔
    user_bot_welcome_msg: Optional[str] = ""  # 群欢迎消息
    
    # 🔥 使用限制设置
    user_bot_restriction_enabled: Optional[bool] = False  # 是否启用使用限制
    user_bot_required_channels: Optional[str] = ""  # 必须关注的频道，换行分隔
    user_bot_required_groups: Optional[str] = ""  # 必须加入的群聊，换行分隔
    user_bot_restriction_cache_ttl: Optional[int] = 120  # 检查结果缓存时间（秒）
    
    # 🎯 频道入库通知
    notify_channels: Optional[str] = ""  # JSON字符串，频道配置列表
    
    # 🎯 入库通知渠道选择
    library_notify_channels: Optional[str] = ""  # JSON字符串，如 ['tg_bot', 'tg_channel', 'wecom']

class PushRequestModel(BaseModel):
    user_id: str
    period: str
    theme: str

class ScheduleRequestModel(BaseModel):
    user_id: str
    period: str
    theme: str

# 🔥 更新：为编辑用户增加高级权限字段
class UserUpdateModel(BaseModel):
    user_id: str
    password: Optional[str] = None
    is_disabled: Optional[bool] = None
    expire_date: Optional[str] = None 
    enable_all_folders: Optional[bool] = None
    enabled_folders: Optional[List[str]] = None
    excluded_sub_folders: Optional[List[str]] = None
    # 高级控制
    enable_downloading: Optional[bool] = None
    enable_video_transcoding: Optional[bool] = None
    enable_audio_transcoding: Optional[bool] = None
    max_parental_rating: Optional[int] = None
# 🔥 新增单用户风控字段
    max_concurrent: Optional[int] = None   # 该用户的专属最大并发数
    is_vip: Optional[bool] = False
    risk_level: Optional[str] = None       # 风控状态(例如：safe, banned)

# 🔥 更新：为新建/套用模板增加颗粒度控制选项
class NewUserModel(BaseModel):
    name: str
    password: Optional[str] = None 
    expire_date: Optional[str] = None
    template_user_id: Optional[str] = None 
    # 颗粒度复制选项
    copy_library: Optional[bool] = True
    copy_policy: Optional[bool] = True
    copy_parental: Optional[bool] = True
# 🔥 新增单用户风控字段
    max_concurrent: Optional[int] = None   # 新用户的默认最大并发数
    is_vip: Optional[bool] = False

class InviteGenModel(BaseModel):
    days: int 
    template_user_id: Optional[str] = None 
    count: Optional[int] = 1

class UserRegisterModel(BaseModel):
    code: str
    username: str
    password: str

class BatchActionModel(BaseModel):
    user_ids: List[str]
    action: str  
    value: Optional[str] = None  

class MediaRequestSubmitModel(BaseModel):
    tmdb_id: int
    media_type: str  
    title: str
    year: str = ""
    poster_path: str = ""
    overview: str = ""

class MediaRequestStatusUpdateModel(BaseModel):
    tmdb_id: int
    status: int  

# 🔥 更新：为批量操作新增颗粒度选项参数
class BatchActionModel(BaseModel):
    user_ids: List[str]
    action: str  
    value: Optional[str] = None  
    copy_library: Optional[bool] = False
    copy_policy: Optional[bool] = False
    copy_parental: Optional[bool] = False