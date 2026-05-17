"""字体加载工具"""
import os
import logging
from PIL import ImageFont
from typing import Optional

logger = logging.getLogger("uvicorn")

# 默认字体目录
FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fonts")

# 系统字体路径（Windows）
SYSTEM_FONTS = [
    "C:/Windows/Fonts/msyh.ttc",      # 微软雅黑
    "C:/Windows/Fonts/simhei.ttf",    # 黑体
    "C:/Windows/Fonts/simsun.ttc",    # 宋体
    "C:/Windows/Fonts/arial.ttf",     # Arial
]


def get_font(font_path: Optional[str] = None, size: int = 48) -> ImageFont.FreeTypeFont:
    """获取字体"""
    # 优先使用指定字体
    if font_path and os.path.exists(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception as e:
            logger.warning(f"加载指定字体失败: {font_path}, {e}")
    
    # 尝试插件自带字体
    for filename in os.listdir(FONT_DIR) if os.path.exists(FONT_DIR) else []:
        if filename.lower().endswith(('.ttf', '.ttc', '.otf')):
            try:
                return ImageFont.truetype(os.path.join(FONT_DIR, filename), size)
            except:
                pass
    
    # 尝试系统字体
    for sys_font in SYSTEM_FONTS:
        if os.path.exists(sys_font):
            try:
                return ImageFont.truetype(sys_font, size)
            except:
                pass
    
    # 使用默认字体
    try:
        return ImageFont.truetype("arial.ttf", size)
    except:
        pass
    
    # 最后使用 PIL 默认
    return ImageFont.load_default()


def get_font_size(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> int:
    """计算适合宽度的字体大小"""
    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    
    if text_width <= max_width:
        return font.size
    
    # 计算缩放比例
    ratio = max_width / text_width
    new_size = int(font.size * ratio)
    
    # 重新加载字体
    try:
        return ImageFont.truetype(font.path, new_size).size
    except:
        return new_size


def measure_text(text: str, font: ImageFont.FreeTypeFont) -> tuple:
    """测量文字尺寸"""
    bbox = font.getbbox(text)
    return (bbox[2] - bbox[0], bbox[3] - bbox[1])
