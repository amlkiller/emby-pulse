import logging
import os

from app.core.config import FONT_PATH

logger = logging.getLogger("uvicorn")

try:
    from PIL import ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    print("⚠️ Pillow not found. Report generation disabled.")


# ==========================================
# 海报主题配置
# ==========================================
POSTER_THEMES = {
    "cinema": {
        "name": "🎞️ 电影胶片",
        "description": "经典电影胶片质感",
        "layout": "film_strip",  # 横排封面 + 胶片孔装饰
        "background": {
            "type": "gradient",
            "colors": [(15, 15, 20), (23, 20, 30)],
        },
        "colors": {
            "title": (255, 255, 255),
            "subtitle": (120, 125, 140),
            "date": (220, 220, 230),
            "weekday": (150, 150, 160),
            "section_title": (255, 255, 255),
            "section_en": (130, 135, 150),
            "rank_bg": (20, 22, 30),
            "rank_1": (255, 215, 0),
            "rank_2": (192, 192, 192),
            "rank_3": (205, 127, 50),
            "rank_other": (180, 185, 195),
            "name": (240, 240, 245),
            "duration": (130, 135, 150),
            "watermark": (80, 85, 100),
            "divider": (60, 65, 80),
            "placeholder_bg": [(45, 48, 58), (60, 60, 68)],
            "placeholder_text": (90, 95, 110),
            "shadow": (10, 12, 18),
            "poster_radius": 12,
        },
        "decorations": ["film_holes", "spotlight", "bottom_glow"],
    },
    
    "magazine": {
        "name": "🎪 瀑布流",
        "description": "交错瀑布流布局",
        "layout": "waterfall",  # 瀑布流布局
        "background": {
            "type": "gradient",
            "colors": [(18, 18, 22), (28, 28, 35)],
        },
        "colors": {
            "title": (255, 255, 255),
            "subtitle": (180, 180, 190),
            "date": (220, 220, 230),
            "weekday": (150, 150, 160),
            "section_title": (255, 255, 255),
            "section_en": (130, 135, 150),
            "rank_bg": (30, 30, 38),
            "rank_1": (255, 215, 0),
            "rank_2": (200, 200, 210),
            "rank_3": (180, 160, 140),
            "rank_other": (150, 150, 160),
            "name": (240, 240, 245),
            "duration": (140, 140, 150),
            "watermark": (100, 100, 110),
            "divider": (50, 50, 60),
            "placeholder_bg": [(35, 35, 42), (45, 45, 55)],
            "placeholder_text": (100, 100, 110),
            "shadow": (10, 10, 15),
            "poster_radius": 10,
            "card_bg": (25, 25, 32),
        },
        "decorations": ["subtle_noise"],
    },
    
    "grid": {
        "name": "📱 卡片网格",
        "description": "现代卡片布局",
        "layout": "card_grid",  # 2列卡片布局
        "background": {
            "type": "gradient",
            "colors": [(245, 247, 250), (235, 238, 245)],
        },
        "colors": {
            "title": (30, 35, 45),
            "subtitle": (100, 110, 130),
            "date": (50, 55, 65),
            "weekday": (100, 110, 130),
            "section_title": (30, 35, 45),
            "section_en": (130, 140, 160),
            "rank_bg": (255, 255, 255),
            "rank_1": (255, 180, 0),
            "rank_2": (180, 180, 190),
            "rank_3": (200, 160, 120),
            "rank_other": (150, 155, 165),
            "name": (40, 45, 55),
            "duration": (100, 110, 130),
            "watermark": (150, 160, 180),
            "divider": (220, 225, 235),
            "placeholder_bg": [(220, 225, 235), (210, 215, 225)],
            "placeholder_text": (160, 170, 185),
            "shadow": (180, 185, 195),
            "poster_radius": 16,
            "card_bg": (255, 255, 255),
            "card_shadow": (200, 205, 215),
        },
        "decorations": ["card_shadows"],
    },
    
    "neon": {
        "name": "💜 霓虹都市",
        "description": "赛博朋克霓虹风格",
        "layout": "film_strip",
        "background": {
            "type": "gradient",
            "colors": [(10, 5, 25), (25, 10, 45)],
        },
        "colors": {
            "title": (255, 50, 200),
            "subtitle": (50, 255, 255),
            "date": (255, 255, 255),
            "weekday": (180, 100, 255),
            "section_title": (255, 100, 255),
            "section_en": (100, 255, 255),
            "rank_bg": (20, 10, 40),
            "rank_1": (255, 255, 0),
            "rank_2": (0, 255, 255),
            "rank_3": (255, 0, 255),
            "rank_other": (200, 200, 255),
            "name": (255, 255, 255),
            "duration": (180, 180, 255),
            "watermark": (100, 50, 150),
            "divider": (100, 50, 150),
            "placeholder_bg": [(30, 15, 50), (50, 25, 70)],
            "placeholder_text": (150, 100, 200),
            "shadow": (5, 0, 20),
            "poster_radius": 8,
        },
        "decorations": ["neon_grid", "glow_borders"],
    },
    
    "list": {
        "name": "📝 简约榜单",
        "description": "纯文字排行列表",
        "layout": "text_list",  # 纯文字列表，无需封面
        "background": {
            "type": "gradient",
            "colors": [(255, 255, 255), (248, 250, 252)],
        },
        "colors": {
            "title": (25, 25, 30),
            "subtitle": (100, 105, 115),
            "date": (60, 65, 75),
            "weekday": (100, 105, 115),
            "section_title": (25, 25, 30),
            "section_en": (140, 145, 155),
            "rank_bg": (245, 247, 250),
            "rank_1": (255, 180, 0),
            "rank_2": (170, 175, 185),
            "rank_3": (200, 150, 100),
            "rank_other": (100, 105, 115),
            "name": (35, 40, 50),
            "duration": (80, 85, 95),
            "watermark": (160, 165, 175),
            "divider": (230, 235, 240),
            "placeholder_bg": [(245, 247, 250), (240, 242, 245)],
            "placeholder_text": (160, 165, 175),
            "shadow": (230, 235, 240),
            "poster_radius": 8,
            "row_bg": (250, 252, 255),
            "row_hover": (245, 247, 250),
        },
        "decorations": ["alternating_rows"],
    },
    
    "poster": {
        "name": "🎬 宣传海报",
        "description": "大图背景宣传风格",
        "layout": "hero_poster",  # 大图背景 + 底部小图
        "background": {
            "type": "gradient",
            "colors": [(15, 15, 20), (25, 25, 35)],
        },
        "colors": {
            "title": (255, 255, 255),
            "subtitle": (180, 180, 200),
            "date": (255, 255, 255),
            "weekday": (200, 200, 210),
            "section_title": (255, 255, 255),
            "section_en": (150, 150, 170),
            "rank_bg": (30, 30, 40),
            "rank_1": (255, 215, 0),
            "rank_2": (200, 200, 220),
            "rank_3": (180, 150, 120),
            "rank_other": (160, 160, 180),
            "name": (255, 255, 255),
            "duration": (180, 180, 200),
            "watermark": (120, 120, 140),
            "divider": (60, 60, 80),
            "placeholder_bg": [(40, 40, 50), (50, 50, 60)],
            "placeholder_text": (100, 100, 120),
            "shadow": (0, 0, 0),
            "poster_radius": 12,
            "hero_overlay": (0, 0, 0),
        },
        "decorations": ["hero_gradient", "frame_border"],
    },
    
    "sunset": {
        "name": "🌅 日落橙",
        "description": "温暖日落渐变",
        "layout": "film_strip",
        "background": {
            "type": "gradient",
            "colors": [(45, 25, 60), (80, 40, 50)],
        },
        "colors": {
            "title": (255, 220, 180),
            "subtitle": (255, 180, 130),
            "date": (255, 240, 220),
            "weekday": (255, 200, 160),
            "section_title": (255, 230, 200),
            "section_en": (255, 190, 150),
            "rank_bg": (60, 35, 55),
            "rank_1": (255, 200, 50),
            "rank_2": (255, 160, 100),
            "rank_3": (255, 120, 80),
            "rank_other": (220, 180, 160),
            "name": (255, 250, 240),
            "duration": (255, 210, 180),
            "watermark": (200, 150, 130),
            "divider": (100, 60, 70),
            "placeholder_bg": [(70, 45, 60), (90, 55, 65)],
            "placeholder_text": (180, 140, 130),
            "shadow": (30, 20, 35),
            "poster_radius": 12,
        },
        "decorations": ["sun_glow", "warm_overlay"],
    },
    
    "ocean": {
        "name": "🌊 深海蓝",
        "description": "深邃海洋风格",
        "layout": "film_strip",
        "background": {
            "type": "gradient",
            "colors": [(5, 20, 40), (10, 35, 60)],
        },
        "colors": {
            "title": (180, 230, 255),
            "subtitle": (100, 180, 220),
            "date": (200, 240, 255),
            "weekday": (150, 200, 230),
            "section_title": (180, 230, 255),
            "section_en": (100, 180, 220),
            "rank_bg": (15, 40, 60),
            "rank_1": (100, 255, 200),
            "rank_2": (80, 200, 255),
            "rank_3": (60, 160, 220),
            "rank_other": (150, 200, 220),
            "name": (220, 245, 255),
            "duration": (150, 200, 230),
            "watermark": (80, 140, 180),
            "divider": (40, 80, 120),
            "placeholder_bg": [(20, 50, 70), (30, 60, 85)],
            "placeholder_text": (100, 160, 200),
            "shadow": (5, 15, 30),
            "poster_radius": 12,
        },
        "decorations": ["wave_lines", "bubbles"],
    },
    
    "forest": {
        "name": "🌲 森林绿",
        "description": "自然清新风格",
        "layout": "film_strip",
        "background": {
            "type": "gradient",
            "colors": [(15, 30, 20), (25, 45, 30)],
        },
        "colors": {
            "title": (200, 255, 200),
            "subtitle": (150, 200, 150),
            "date": (180, 230, 180),
            "weekday": (140, 190, 140),
            "section_title": (200, 255, 200),
            "section_en": (140, 200, 140),
            "rank_bg": (20, 40, 25),
            "rank_1": (100, 255, 100),
            "rank_2": (150, 220, 100),
            "rank_3": (180, 200, 100),
            "rank_other": (160, 190, 160),
            "name": (220, 250, 220),
            "duration": (160, 200, 160),
            "watermark": (80, 130, 80),
            "divider": (50, 80, 50),
            "placeholder_bg": [(30, 50, 35), (40, 60, 45)],
            "placeholder_text": (100, 150, 110),
            "shadow": (10, 20, 15),
            "poster_radius": 12,
        },
        "decorations": ["leaf_pattern"],
    },
}


def get_theme_list():
    """获取可用主题列表"""
    return [{"id": k, "name": v["name"], "description": v["description"]} for k, v in POSTER_THEMES.items()]


# 全局字体缓存
_font_cache = {}

def _get_font(size):
    """获取字体（带缓存）"""
    cache_key = f"font_{size}"
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    font = _load_font(size)
    _font_cache[cache_key] = font
    return font

def _load_font(size):
    """加载字体 - 优先级：内置字体 > 用户上传字体 > 系统字体 > 默认"""
    # 1. 优先使用插件内置字体（Docker 路径）
    builtin_paths = [
        "/workspace/app/plugins/view_report/fonts/NotoSansCJKsc-Bold.otf",
        "/app/app/plugins/view_report/fonts/NotoSansCJKsc-Bold.otf",
    ]
    for builtin_path in builtin_paths:
        if os.path.exists(builtin_path):
            try:
                return ImageFont.truetype(builtin_path, size)
            except Exception as e:
                logger.debug(f"内置字体加载失败: {e}")

    # 2. 用户上传的字体
    if os.path.exists(FONT_PATH):
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except:
            pass

    # 3. 系统字体
    system_fonts = [
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "C:\\Windows\\Fonts\\msyh.ttc",
        "C:\\Windows\\Fonts\\simhei.ttf",
        "C:\\Windows\\Fonts\\simsun.ttc",
    ]
    for sys_font in system_fonts:
        if os.path.exists(sys_font):
            try:
                return ImageFont.truetype(sys_font, size)
            except:
                continue
    return ImageFont.load_default()
