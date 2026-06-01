"""
自定义通知模板插件 (Pro 专享)
内置多种风格模板，每种风格包含完整字段，支持随机文案和评分动态
"""
import logging
import random
import re
from app.plugins.base import PluginBase

logger = logging.getLogger("uvicorn")

# 默认模板
DEFAULT_TEMPLATES = {
    "library_new_episode": "📺 <b>新入库 剧集 {series_name}</b> {episode_info}\n\n{quality_icon} <b>质量：</b>{quality}  |  ⭐ 评分：{rating}\n📌 年份：{year}  |  🎬 编码：{video_codec}\n🕒 时间：{time}\n\n📝 <b>剧情简介：</b>\n{overview}",
    "library_new_item": "{type_icon} <b>新入库 {type_cn} {name}</b> ({year})\n\n{quality_icon} <b>质量：</b>{quality}  |  ⭐ 评分：{rating} / 10\n🎬 <b>编码：</b>{video_codec} {audio_codec}\n🕒 时间：{time}\n\n📝 <b>剧情简介：</b>\n{overview}",
    "playback_start": "▶️ <b>【{username}】开始播放 {type_cn} {title}</b>{ep_info}\n\n⭐ <b>评分：</b>{rating} ｜ 📚 <b>类型：</b>{type_cn}\n🔄 <b>进度：</b>{progress}\n🌐 <b>IP地址：</b>{ip} {location}\n📱 <b>设备：</b>{client} {device}\n🕒 <b>时间：</b>{time}\n\n📝 <b>剧情：</b>{overview}",
    "playback_stop": "⏹️ <b>【{username}】停止播放 {type_cn} {title}</b>{ep_info}\n\n⭐ <b>评分：</b>{rating} ｜ 📚 <b>类型：</b>{type_cn}\n🔄 <b>进度：</b>{progress}\n🌐 <b>IP地址：</b>{ip} {location}\n📱 <b>设备：</b>{client} {device}\n🕒 <b>时间：</b>{time}\n\n📝 <b>剧情：</b>{overview}",
}

TEMPLATE_VARS = {
    "library_new_episode": ["{series_name}", "{episode_info}", "{year}", "{rating}", "{time}", "{overview}", "{quality}", "{quality_icon}", "{video_codec}", "{audio_codec}", "{resolution}", "{hdr}"],
    "library_new_item": ["{name}", "{type_icon}", "{type_cn}", "{year}", "{rating}", "{time}", "{overview}", "{quality}", "{quality_icon}", "{video_codec}", "{audio_codec}", "{resolution}", "{hdr}"],
    "playback_start": ["{username}", "{title}", "{ep_info}", "{type_cn}", "{rating}", "{progress}", "{ip}", "{location}", "{client}", "{device}", "{time}", "{overview}"],
    "playback_stop": ["{username}", "{title}", "{ep_info}", "{type_cn}", "{rating}", "{progress}", "{ip}", "{location}", "{client}", "{device}", "{time}", "{overview}"],
}

# ==========================================
# 风格模板库（每种风格、每种通知类型多条完整模板）
# ==========================================
STYLE_TEMPLATES = {
    "anime": {
        "playback_start": [
            "<b>🎀 叮咚~ 异世界传送门已开启！</b>\n\n欢迎回来，{username} 主人！(๑•̀ㅂ•́)و✧\n本大王已经为您准备好最新的精神食粮啦，快快坐好，准备开启新一轮的冒险吧！\n\n📺 <b>正在为您放映：</b>《{title}》{ep_info}\n✨ <b>类型鉴定：</b>{type_cn} | ⭐ <b>羁绊星级：</b>{rating} 分\n⏳ <b>同步进度：</b>{progress}\n📖 <b>来自异世界的传说：</b>\n> {overview}\n\n📡 <b>时空信标追踪中...</b>\n\n📍 <b>召唤阵位置：</b>{location} (IP: {ip})\n⚔️ <b>咏唱法器：</b>{device}\n🔮 <b>连接终端：</b>{client}\n⏱️ <b>传送时间：</b>{time}\n\n祝您观影愉快喵~ 🐾",
            "<b>🌟 {username} 的追番时间到！冲鸭~</b>\n\n今天也要元气满满地看片呢！ヾ(≧▽≦*)o\n快来看看这次是什么宝藏作品吧！\n\n📺 <b>本期放映：</b>《{title}》{ep_info}\n✨ <b>属性鉴定：</b>{type_cn} | ⭐ <b>战斗力：</b>{rating} 分\n⏳ <b>冒险进度：</b>{progress}\n📖 <b>世界观速览：</b>\n> {overview}\n\n📡 <b>信号捕获中...</b>\n\n📍 <b>坐标：</b>{location} (IP: {ip})\n📱 <b>装备：</b>{device} · {client}\n⏱️ <b>开播时间：</b>{time}\n\n冲冲冲！(ﾉ◕ヮ◕)ﾉ*:・ﾟ✧",
            "<b>💫 {username} 又双叒叕开始看片了呢~</b>\n\n这次是什么宝藏作品呀？让我康康！\n\n📺 <b>正在播放：</b>《{title}》{ep_info}\n✨ <b>类型：</b>{type_cn} | ⭐ <b>评分：</b>{rating} 分\n⏳ <b>进度：</b>{progress}\n📖 <b>简介：</b>\n> {overview}\n\n📡 <b>定位中...</b>\n\n📍 <b>位置：</b>{location} (IP: {ip})\n📱 <b>设备：</b>{device} · {client}\n⏱️ <b>时间：</b>{time}\n\n要好好享受哦~ ✨",
        ],
        "playback_stop": [
            "<b>💤 叮咚~ 异世界的探险暂时告一段落啦！</b>\n\n辛苦啦，{username} 主人！( ´ ▽ ` )ﾉ\n您的冒险档案已经妥善保存！无论是去三次元忙碌，还是准备好好休息，本大王都会乖乖在这里等您再次开启传送门的哦！\n\n📺 <b>本次观测对象：</b>《{title}》{ep_info}\n✨ <b>类型鉴定：</b>{type_cn} | ⭐ <b>羁绊星级：</b>{rating} 分\n💾 <b>安全存档进度：</b>{progress}\n📖 <b>本期冒险回顾：</b>\n> {overview}\n\n🔌 <b>时空信标已断开...</b>\n\n📍 <b>登出阵位置：</b>{location} (IP: {ip})\n⚔️ <b>收起法器：</b>{device}\n🔮 <b>断开终端：</b>{client}\n⏱️ <b>脱离时间：</b>{time}\n\n期待与您的下一次相遇喵，记得好好补充能量~ 🐾",
            "<b>🌙 {username} 的观影之旅暂时告一段落~</b>\n\n今天的份额用完啦！(｡•́︿•̀｡)\n别担心，进度已经帮你记好了，下次可以无缝衔接哦！\n\n📺 <b>刚刚在看：</b>《{title}》{ep_info}\n✨ {type_cn} | ⭐ {rating} 分\n💾 <b>存档点：</b>{progress}\n📖 <b>回顾：</b>\n> {overview}\n\n📍 {location} (IP: {ip})\n📱 {device} · {client}\n⏱️ {time}\n\n明天继续冒险吧~ 晚安喵 🌟",
        ],
        "library_new_episode": [
            "<b>🎉 叮咚~ 新番收容成功！</b>\n\n仓库又进新货了呢！快来看看是什么宝藏！✨\n\n📺 <b>新番收容：</b>《{series_name}》{episode_info}\n{quality_icon} <b>画质：</b>{quality} | ⭐ <b>初始星级：</b>{rating} 分\n📅 {year} | 🎬 {video_codec}\n📖 <b>世界观情报：</b>\n> {overview}\n\n📡 <b>入库档案生成中...</b>\n\n💾 <b>收容状态：</b>100% 捕获成功！\n⏱️ <b>捕获时间：</b>{time}\n\n粮仓已扩充，今天也是被喜欢的事物包围的一天喵~ 🐾",
            "<b>💖 新的宝藏已入库！</b>\n\n快去发现吧！(ﾉ◕ヮ◕)ﾉ*:・ﾟ✧\n\n📺 <b>{series_name}</b> {episode_info}\n{quality_icon} {quality} | ⭐ {rating} 分\n📅 {year} | 🎬 {video_codec}\n📖 {overview}\n\n💾 入库完成！\n⏱️ {time}\n\n又多了一部可以追的番~ ✨",
        ],
        "library_new_item": [
            "<b>✨ 叮咚~ 新作品已成功收容！</b>\n\n{type_icon} <b>收容对象：</b>《{name}》({year})\n{quality_icon} <b>画质：</b>{quality} | ⭐ <b>初始星级：</b>{rating} 分\n🎬 {video_codec} {audio_codec}\n📖 <b>情报：</b>\n> {overview}\n\n💾 收容状态：100% 成功！\n⏱️ {time}\n\n片库又丰富了呢~ 🐾",
        ],
    },
    "humor": {
        "playback_start": [
            "<b>🍿 警报！{username} 又开始摸鱼看片了！</b>\n\n老板看到会哭的好吧...算了，快乐最重要\n\n📺 <b>摸鱼内容：</b>《{title}》{ep_info}\n📚 <b>类型：</b>{type_cn} | ⭐ <b>豆瓣可能给：</b>{rating} 分\n⏳ <b>摸鱼进度：</b>{progress}\n📖 <b>剧情简介（方便你跟同事吹牛）：</b>\n> {overview}\n\n🕵️ <b>摸鱼现场还原...</b>\n\n📍 <b>作案地点：</b>{location} (IP: {ip})\n📱 <b>作案工具：</b>{device}\n🔮 <b>帮凶软件：</b>{client}\n⏱️ <b>作案时间：</b>{time}\n\n温馨提示：别忘了锁屏 🔒",
            "<b>📺 {username} 的快乐源泉上线了</b>\n\n工作是老板的，快乐是自己的，这波不亏\n\n🎬 <b>今日精神食粮：</b>《{title}》{ep_info}\n📚 {type_cn} | ⭐ {rating} 分\n⏳ {progress}\n📖 {overview}\n\n📍 <b>据点：</b>{location} (IP: {ip})\n📱 <b>装备：</b>{device} · {client}\n⏱️ {time}\n\n看完记得写周报 📝",
            "<b>🛋️ {username} 已就位，准备开始精神食粮补给</b>\n\n今天的 KPI 就是把这部看完\n\n📺 《{title}》{ep_info}\n📚 {type_cn} | ⭐ {rating} 分\n⏳ {progress}\n📖 {overview}\n\n📍 {location} (IP: {ip})\n📱 {device} · {client}\n⏱️ {time}\n\n加油，你是最棒的（摸鱼人）💪",
        ],
        "playback_stop": [
            "<b>💤 {username} 终于舍得关了</b>\n\n是困了？还是被发现摸鱼了？还是良心发现要去工作了？\n\n📺 <b>刚才在看：</b>《{title}》{ep_info}\n📚 {type_cn} | ⭐ {rating} 分\n⏳ <b>看到：</b>{progress}\n📖 {overview}\n\n📍 {location} (IP: {ip})\n📱 {device} · {client}\n⏱️ {time}\n\n下次摸鱼记得关好门 🚪",
            "<b>⏸️ {username} 按下了暂停键</b>\n\n大概是去上厕所了吧...或者泡面熟了\n\n📺 《{title}》{ep_info}\n⭐ {rating} 分 | ⏳ {progress}\n📖 {overview}\n\n📍 {location} (IP: {ip})\n📱 {device}\n⏱️ {time}\n\n别走太久，剧情不等人 🏃",
        ],
        "library_new_episode": [
            "<b>📦 又有新片入库了，硬盘在哭泣</b>\n\n钱包：我还好吗？硬盘：我快满了...\n\n📺 <b>{series_name}</b> {episode_info}\n{quality_icon} {quality} | ⭐ {rating} 分\n📅 {year} | 🎬 {video_codec}\n📖 {overview}\n\n💾 入库成功，硬盘又少了一点空间\n⏱️ {time}\n\n存都存了，不看白不看 🤷",
        ],
        "library_new_item": [
            "<b>📀 新资源到货，请签收</b>\n\n快递小哥（服务器）已送达\n\n{type_icon} <b>{name}</b> ({year})\n{quality_icon} {quality} | ⭐ {rating} 分\n🎬 {video_codec} {audio_codec}\n📖 {overview}\n\n💾 已入库\n⏱️ {time}\n\n又多了一个「改天再看」的片子 📋",
        ],
    },
    "cold": {
        "playback_start": [
            "▶️ <b>{username}</b> · {title}{ep_info}\n\n{type_cn} | ⭐ {rating}\n⏳ {progress}\n📖 {overview}\n\n📍 {location} ({ip})\n📱 {device} · {client}\n⏱️ {time}",
            "▶️ {username} 正在播放\n\n<b>{title}</b>{ep_info}\n{type_cn} · {rating} · {progress}\n\n{overview}\n\n{location} · {device} · {client}\n{time}",
        ],
        "playback_stop": [
            "⏹️ <b>{username}</b> · {title}{ep_info}\n\n⏳ {progress}\n📖 {overview}\n\n📍 {location} ({ip})\n📱 {device} · {client}\n⏱️ {time}",
            "⏹️ {username} 停止播放\n\n<b>{title}</b>{ep_info}\n{progress}\n\n{location} · {device}\n{time}",
        ],
        "library_new_episode": [
            "📺 <b>{series_name}</b> {episode_info}\n{quality_icon} {quality} | ⭐ {rating}\n📅 {year} | 🎬 {video_codec}\n{overview}\n{time}",
        ],
        "library_new_item": [
            "{type_icon} <b>{name}</b> ({year})\n{quality_icon} {quality} | ⭐ {rating}\n🎬 {video_codec} {audio_codec}\n{overview}\n{time}",
        ],
    },
    "ancient": {
        "playback_start": [
            "<b>📜 {username} 焚香净手，开卷观影</b>\n\n堂前光影徐来，一幕好戏正酣。且看今日所映何物——\n\n🎭 <b>剧目：</b>《{title}》{ep_info}\n📚 <b>品类：</b>{type_cn} | ⭐ <b>品鉴：</b>{rating} 分\n⏳ <b>观至：</b>{progress}\n📖 <b>梗概：</b>\n> {overview}\n\n📜 <b>卷末附录</b>\n\n🏮 <b>所在：</b>{location} (IP: {ip})\n🖌️ <b>器具：</b>{device}\n🔮 <b>法器：</b>{client}\n⏱️ <b>时辰：</b>{time}\n\n愿此光影，慰君心怀 🏮",
            "<b>🏮 {username} 于堂前点映《{title}》</b>\n\n{ep_info}\n良辰美景，不可辜负\n\n📚 {type_cn} | ⭐ {rating} 分\n⏳ {progress}\n📖 {overview}\n\n🏮 {location} (IP: {ip})\n🖌️ {device} · {client}\n⏱️ {time}\n\n且观且珍惜 📿",
        ],
        "playback_stop": [
            "<b>🌙 {username} 拂袖而去，光影渐隐</b>\n\n今日观影至此，且待来日再续。卷轴已收，灯火阑珊——\n\n🎭 <b>方才所观：</b>《{title}》{ep_info}\n📚 {type_cn} | ⭐ {rating} 分\n⏳ <b>止于：</b>{progress}\n📖 <b>回顾：</b>\n> {overview}\n\n🏮 {location} (IP: {ip})\n🖌️ {device} · {client}\n⏱️ {time}\n\n山高水长，后会有期 🏔️",
            "<b>📿 {username} 合卷而叹，意犹未尽</b>\n\n好戏虽暂歇，余韵绕梁三日\n\n🎭 《{title}》{ep_info}\n⭐ {rating} 分 | ⏳ {progress}\n📖 {overview}\n\n🏮 {location} · {device}\n⏱️ {time}\n\n来日方长 🌙",
        ],
        "library_new_episode": [
            "<b>📜 新卷入藏，珍本已至</b>\n\n藏经阁又添新典，诸位可前往一观\n\n📺 <b>{series_name}</b> {episode_info}\n{quality_icon} <b>画质：</b>{quality} | ⭐ {rating} 分\n📅 {year} | 🎬 {video_codec}\n📖 {overview}\n\n💾 已入藏\n⏱️ {time}\n\n开卷有益，善哉善哉 📿",
        ],
        "library_new_item": [
            "<b>🏮 藏经阁新增典籍一卷</b>\n\n{type_icon} <b>《{name}》</b>({year})\n{quality_icon} {quality} | ⭐ {rating} 分\n🎬 {video_codec} {audio_codec}\n📖 {overview}\n\n💾 已入藏\n⏱️ {time}\n\n天下文章，尽收于此 📜",
        ],
    },
}


class NotifyTemplatePlugin(PluginBase):
    id = "notify_template"
    name = "自定义通知模板"
    description = "自定义机器人入库通知和播放通知的文字排版风格"
    icon = "fa-palette"
    icon_color = "from-rose-500 to-orange-500"
    version = "1.1.0"
    author = "EmbyPulse"

    def on_enable(self):
        logger.info("🔌 [通知模板] 插件已启用")

    def on_disable(self):
        logger.info("🔌 [通知模板] 插件已禁用")

    def get_config_schema(self):
        return [
            {"key": "style", "label": "通知风格", "type": "select", "options": [
                {"value": "default", "label": "📋 默认 — 标准通知风格"},
                {"value": "anime", "label": "🌸 二次元 — 可爱活泼，每次随机文案"},
                {"value": "humor", "label": "😂 幽默 — 搞笑吐槽，每次随机文案"},
                {"value": "cold", "label": "🧊 高冷 — 极简信息"},
                {"value": "ancient", "label": "🏯 古风 — 文言古韵，每次随机文案"},
                {"value": "custom", "label": "✏️ 自定义 — 使用下方自定义模板"},
            ]},
            {"key": "playback_start", "label": "✏️ 自定义·开始播放", "type": "textarea",
             "placeholder": "选择「自定义」风格后生效。可用变量：{username} {title} {ep_info} {type_cn} {rating} {progress} {ip} {location} {client} {device} {time} {overview}"},
            {"key": "playback_stop", "label": "✏️ 自定义·停止播放", "type": "textarea",
             "placeholder": "选择「自定义」风格后生效"},
            {"key": "library_new_episode", "label": "✏️ 自定义·剧集入库", "type": "textarea",
             "placeholder": "选择「自定义」风格后生效。可用变量：{series_name} {episode_info} {year} {rating} {time} {overview} {quality} {quality_icon} {video_codec} {audio_codec} {resolution} {hdr}"},
            {"key": "library_new_item", "label": "✏️ 自定义·电影入库", "type": "textarea",
             "placeholder": "选择「自定义」风格后生效"},
            {"key": "notify_enabled", "label": "启用通知", "type": "toggle", "hint": "开启后，插件运行状态会发送到全局通知"},
        ]

    def _get_config(self):
        from app.plugins import get_plugin_config
        return get_plugin_config(self.id)

    def get_template(self, template_key, variables=None):
        """获取模板，根据风格随机选择"""
        if not self._enabled:
            return DEFAULT_TEMPLATES.get(template_key, "")
        config = self._get_config()
        style_raw = config.get("style", "default")
        style = style_raw.strip() if style_raw else "default"

        if style == "custom":
            custom = config.get(template_key, "").strip()
            if custom:
                return custom
            return DEFAULT_TEMPLATES.get(template_key, "")

        if style == "default":
            return DEFAULT_TEMPLATES.get(template_key, "")

        # 从风格模板库随机选一条
        style_tpls = STYLE_TEMPLATES.get(style, {}).get(template_key, [])
        if not style_tpls:
            return DEFAULT_TEMPLATES.get(template_key, "")
        return random.choice(style_tpls)

    def render(self, template_key, variables):
        """渲染模板，空字段所在行自动隐藏"""
        tpl = self.get_template(template_key, variables)
        try:
            # 先替换所有变量
            for k, v in variables.items():
                tpl = tpl.replace("{" + k + "}", str(v) if v else "")
            
            # 处理空字段：如果某行包含空字段标记，则隐藏该行
            lines = tpl.split("\n")
            filtered_lines = []
            for line in lines:
                stripped = line.strip()
                
                # 检查质量行："质量：</b>  |" 或 "质量：</b>" 后面没有内容
                if "质量：</b>" in line or "质量:" in line:
                    # 检查是否为空值：质量：</b> 后面只有空格和分隔符
                    if re.search(r'质量：</b>\s*[|｜]', line) or re.search(r'质量：</b>\s*$', line):
                        continue
                    # 检查是否只有图标和质量标签，没有实际值
                    if re.search(r'质量：</b>\s+\|', line):
                        continue
                
                # 检查编码行："编码：</b>" 后面没有内容
                if "编码：</b>" in line or "编码:" in line:
                    if re.search(r'编码：</b>\s*$', line) or re.search(r'编码：</b>\s+$', line):
                        continue
                
                # 检查是否整行只有空的质量/编码信息
                # 格式如: "🎬 <b>质量：</b>  |  ⭐ 评分："
                if re.match(r'^[🎬📺📱💾📼✨⭐📌🕒📝\s<>b/]+(质量|编码)[:：]</b>\s*[|｜]*\s*[⭐📌🕒\s<>b/]*$', stripped):
                    continue
                
                filtered_lines.append(line)
            tpl = "\n".join(filtered_lines)
        except Exception as e:
            logger.warning(f"[模板渲染] 错误: {e}")
        return tpl

    def preview(self, template_key, template_text=""):
        """预览模板"""
        sample = {
            "series_name": "权力的游戏", "episode_info": "S08E06",
            "name": "沙丘2", "type_icon": "🎬", "type_cn": "电影",
            "year": "2024", "rating": "8.5", "time": "2026-03-18 15:30",
            "overview": "保罗·厄崔迪与弗里曼人联合...",
            "username": "张三", "title": "沙丘2", "ep_info": "",
            "progress": "01:23:45 / 02:46:00 (50%)",
            "ip": "192.168.1.100", "location": "局域网",
            "client": "Infuse", "device": "iPhone 15 Pro",
            "quality": "4K HDR", "quality_icon": "✨",
            "video_codec": "HEVC", "audio_codec": "DTS-HD MA 7.1",
            "resolution": "3840×2160", "hdr": "HDR"
        }
        tpl = template_text.strip() if template_text else self.get_template(template_key)
        for k, v in sample.items():
            tpl = tpl.replace("{" + k + "}", v)
        return tpl
