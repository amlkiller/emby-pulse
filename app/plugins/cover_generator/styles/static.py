"""静态风格生成器 - 优化版"""
import os
import io
import base64
import random
import colorsys
import math
from collections import Counter
from typing import List, Optional, Dict, Any, Tuple
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
import numpy as np

from .base import BaseStyle

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BUILTIN_FONT_PATH = os.path.join(PROJECT_ROOT, "plugins", "view_report", "fonts", "NotoSansCJKsc-Bold.otf")


def get_font(size: int) -> ImageFont.FreeTypeFont:
    if os.path.exists(BUILTIN_FONT_PATH):
        try:
            return ImageFont.truetype(BUILTIN_FONT_PATH, size)
        except:
            pass
    for path in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()


def extract_color(image: Image.Image) -> Tuple[int, int, int]:
    """提取图片主色调"""
    img = image.copy()
    img.thumbnail((100, 100))
    img = img.convert('RGB')
    pixels = list(img.getdata())
    
    # 过滤太亮太暗的
    valid = [p for p in pixels if 30 < sum(p) / 3 < 230]
    if not valid:
        valid = pixels
    
    # 统计颜色
    counter = Counter(valid)
    common = counter.most_common(20)
    
    # 找一个饱和度适中的颜色
    for color, _ in common:
        r, g, b = color
        # 计算饱和度
        max_c = max(r, g, b)
        min_c = min(r, g, b)
        if max_c > 0:
            sat = (max_c - min_c) / max_c
            if 0.2 < sat < 0.7:  # 中等饱和度
                return color
    
    # 默认取最常见的
    return common[0][0] if common else (100, 100, 100)


def darken(color: Tuple[int, int, int], factor: float = 0.7) -> Tuple[int, int, int]:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def lighten(color: Tuple[int, int, int], factor: float = 1.3) -> Tuple[int, int, int]:
    return (min(255, int(color[0] * factor)), 
            min(255, int(color[1] * factor)), 
            min(255, int(color[2] * factor)))


def adjust_saturation(color: Tuple[int, int, int], target_sat: float = 0.4) -> Tuple[int, int, int]:
    """调整颜色饱和度"""
    r, g, b = [x / 255.0 for x in color]
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    s = target_sat
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return (int(r * 255), int(g * 255), int(b * 255))


def get_title_color(params: Dict[str, Any], bg_color: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """获取标题颜色"""
    title_color_mode = params.get("title_color_mode", "white")
    title_color_custom = params.get("title_color_custom", [255, 255, 255])
    
    if title_color_mode == "black":
        return (0, 0, 0)
    elif title_color_mode == "custom":
        return tuple(title_color_custom)
    elif title_color_mode == "auto":
        # 根据背景亮度自动选择
        brightness = sum(bg_color) / 3
        return (0, 0, 0) if brightness > 128 else (255, 255, 255)
    else:  # white
        return (255, 255, 255)


# ========== 字体大小模板 ==========
# 根据标题长度和字体大小模式返回字号
FONT_SIZE_TEMPLATES = {
    "large": {
        "short": 180,   # <=4字
        "medium": 140,  # 5-6字
        "long": 100,    # >6字
        "subtitle": 56,
        "line_width": 100,
    },
    "medium": {
        "short": 160,   # <=4字
        "medium": 120,  # 5-6字
        "long": 90,     # >6字
        "subtitle": 48,
        "line_width": 80,
    },
    "small": {
        "short": 130,   # <=4字
        "medium": 100,  # 5-6字
        "long": 75,     # >6字
        "subtitle": 36,
        "line_width": 60,
    },
}


def get_font_size(title: str, font_size_mode: str = "medium") -> Tuple[int, int, int]:
    """根据标题长度和字体大小模式返回字号
    
    Args:
        title: 标题文本
        font_size_mode: large/medium/small
    
    Returns:
        (main_font_size, subtitle_font_size, line_width)
    """
    template = FONT_SIZE_TEMPLATES.get(font_size_mode, FONT_SIZE_TEMPLATES["medium"])
    
    title_len = len(title)
    if title_len <= 4:
        main_size = template["short"]
    elif title_len <= 6:
        main_size = template["medium"]
    else:
        main_size = template["long"]
    
    return main_size, template["subtitle"], template["line_width"]


# ========== 风格1：卡片堆叠 ==========

class Style1CardStack(BaseStyle):
    id = "style1"
    name = "卡片堆叠"
    description = "左侧标题，右侧多层卡片"
    is_animated = False
    
    def generate(self, images: List[Image.Image]) -> Image.Image:
        width, height = 1920, 1080
        title = self.params.get("title", "媒体库")
        subtitle = self.params.get("subtitle", "")
        
        # 背景配置
        bg_mode = self.params.get("bg_mode", "auto")
        bg_preset = self.params.get("bg_preset", 0)
        bg_custom = self.params.get("bg_custom", None)
        
        # 内置预设背景
        preset_colors = [
            (66, 133, 244),   # 蓝色
            (234, 67, 53),    # 红色
            (251, 188, 5),    # 黄色
            (52, 168, 83),    # 绿色
            (156, 39, 176),   # 紫色
            (255, 152, 0),    # 橙色
            (0, 188, 212),    # 青色
            (233, 30, 99),    # 粉色
        ]
        
        if not images:
            raise ValueError("需要图片")
        
        while len(images) < 4:
            images = images + images
        images = images[:4]
        
        # 确定背景颜色
        if bg_mode == "custom" and bg_custom:
            main_color = tuple(bg_custom)
        elif bg_mode == "preset":
            main_color = preset_colors[bg_preset % len(preset_colors)]
        elif bg_mode == "random":
            main_color = random.choice(preset_colors)
        else:
            main_color = extract_color(images[0])
        
        bg_color = darken(main_color, 0.35)
        
        canvas = Image.new("RGB", (width, height), bg_color)
        bg = images[0].convert("RGB").resize((width, height), Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(50))
        
        bg_arr = np.array(bg, dtype=np.float32)
        color_arr = np.array([[bg_color]], dtype=np.float32)
        blended = bg_arr * 0.2 + color_arr * 0.8
        canvas = Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8)).convert("RGBA")
        
        card_size = int(height * 0.55)
        configs = [
            (2, -25, -120, 80, 0.85),
            (3, 20, 100, -60, 0.85),
            (1, -12, -50, 40, 0.92),
            (0, 0, 0, 0, 1.0),
        ]
        
        for img_idx, rotation, x_offset, y_offset, scale in configs:
            card = images[img_idx].convert("RGB")
            actual_size = int(card_size * scale)
            card = ImageOps.fit(card, (actual_size, actual_size), Image.LANCZOS)
            
            mask = Image.new('L', (actual_size, actual_size), 0)
            ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (actual_size, actual_size)], radius=actual_size // 10, fill=255)
            
            card_rgba = Image.new("RGBA", (actual_size, actual_size), (0, 0, 0, 0))
            card_rgba.paste(card, (0, 0))
            card_rgba.putalpha(mask)
            
            shadow = Image.new("RGBA", (actual_size + 40, actual_size + 40), (0, 0, 0, 0))
            shadow_layer = Image.new("RGBA", (actual_size, actual_size), (0, 0, 0, 60))
            shadow_mask = Image.new('L', (actual_size, actual_size), 0)
            ImageDraw.Draw(shadow_mask).rounded_rectangle([(0, 0), (actual_size, actual_size)], radius=actual_size // 10, fill=255)
            shadow_layer.putalpha(shadow_mask)
            shadow.paste(shadow_layer, (20, 20))
            shadow = shadow.filter(ImageFilter.GaussianBlur(20))
            shadow.paste(card_rgba, (15, 15), card_rgba)
            
            if rotation != 0:
                shadow = shadow.rotate(rotation, Image.BICUBIC, expand=True)
            
            center_x = width - card_size // 2 - 200
            center_y = height // 2
            pos_x = center_x - shadow.width // 2 + x_offset
            pos_y = center_y - shadow.height // 2 + y_offset
            
            canvas.paste(shadow, (pos_x, pos_y), shadow)
        
        draw = ImageDraw.Draw(canvas)
        
        # 获取字体大小模板
        font_size_mode = self.params.get("font_size_mode", "medium")
        font_size, sub_font_size, line_width = get_font_size(title, font_size_mode)
        font = get_font(font_size)
        
        bbox = font.getbbox(title)
        text_h = bbox[3] - bbox[1]
        
        x = 120
        y = (height - text_h) // 2 - 40
        
        # 获取标题颜色
        title_color = get_title_color(self.params, bg_color)
        
        # 横线在标题上方
        draw.rectangle([(x, y - 35), (x + line_width, y - 31)], fill=title_color + (200,))
        
        # 主标题
        draw.text((x, y), title, font=font, fill=title_color + (255,))
        
        # 副标题
        if subtitle:
            sub_font = get_font(sub_font_size)
            sub_color = tuple(int(c * 0.85) for c in title_color)
            draw.text((x, y + text_h + 50), subtitle, font=sub_font, fill=sub_color + (255,))
        
        return canvas.convert("RGB")


# ========== 风格2：斜线分割 ==========

class Style2Diagonal(BaseStyle):
    id = "style2"
    name = "斜线分割"
    description = "斜线分割，横版封面"
    is_animated = False
    
    def generate(self, images: List[Image.Image]) -> Image.Image:
        width, height = 1920, 1080
        title = self.params.get("title", "媒体库")
        subtitle = self.params.get("subtitle", "")
        
        # 背景配置
        bg_mode = self.params.get("bg_mode", "auto")
        bg_preset = self.params.get("bg_preset", 0)
        bg_custom = self.params.get("bg_custom", None)
        
        # 内置预设背景
        preset_colors = [
            (66, 133, 244),   # 蓝色
            (234, 67, 53),    # 红色
            (251, 188, 5),    # 黄色
            (52, 168, 83),    # 绿色
            (156, 39, 176),   # 紫色
            (255, 152, 0),    # 橙色
            (0, 188, 212),    # 青色
            (233, 30, 99),    # 粉色
        ]
        
        # 确定背景颜色
        if bg_mode == "custom" and bg_custom:
            main_color = tuple(bg_custom)
        elif bg_mode == "preset":
            main_color = preset_colors[bg_preset % len(preset_colors)]
        elif bg_mode == "random":
            main_color = random.choice(preset_colors)
        else:
            # auto: 从海报提取
            if images:
                main_color = extract_color(images[0])
            else:
                main_color = preset_colors[0]
        
        if not images:
            raise ValueError("需要图片")
        
        img = images[0].convert("RGB")
        bg_color = darken(main_color, 0.35)
        
        canvas = Image.new("RGB", (width, height), bg_color)
        
        # 横版封面铺满整个海报
        cover = ImageOps.fit(img, (width, height), Image.LANCZOS)
        canvas.paste(cover, (0, 0))
        
        canvas = canvas.convert("RGBA")
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        mask_draw = ImageDraw.Draw(overlay)
        
        # 原来的斜切遮罩位置
        points = [
            (0, 0),
            (int(width * 0.45), 0),
            (int(width * 0.55), height),
            (0, height)
        ]
        mask_draw.polygon(points, fill=bg_color + (240,))
        
        canvas = Image.alpha_composite(canvas, overlay)
        
        # 原来的阴影位置
        shadow_mask = Image.new('L', (width, height), 0)
        shadow_draw = ImageDraw.Draw(shadow_mask)
        shadow_draw.polygon([
            (int(width * 0.45) - 5, 0),
            (int(width * 0.45) + 15, 0),
            (int(width * 0.55) + 15, height),
            (int(width * 0.55) - 5, height),
        ], fill=100)
        shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(10))
        
        shadow_layer = Image.new('RGBA', (width, height), darken(bg_color, 0.5) + (255,))
        shadow_layer.putalpha(shadow_mask)
        canvas = Image.alpha_composite(canvas, shadow_layer)
        
        draw = ImageDraw.Draw(canvas)
        
        # 获取字体大小模板
        font_size_mode = self.params.get("font_size_mode", "medium")
        font_size, sub_font_size, line_width = get_font_size(title, font_size_mode)
        font = get_font(font_size)
        
        # 获取文字边界，考虑左侧偏移
        bbox = font.getbbox(title)
        text_h = bbox[3] - bbox[1]
        text_left = bbox[0]  # 左侧偏移
        
        # 原来的标题位置
        x = 100
        y = (height - text_h) // 2 - 40
        
        # 获取标题颜色
        title_color = get_title_color(self.params, bg_color)
        
        # 横线在标题上方，和标题左对齐
        draw.rectangle([(x, y - 30), (x + line_width, y - 26)], fill=title_color + (220,))
        
        # 主标题
        draw.text((x, y), title, font=font, fill=title_color + (255,))
        
        # 副标题，和主标题左对齐
        if subtitle:
            sub_font = get_font(sub_font_size)
            sub_bbox = sub_font.getbbox(subtitle)
            sub_left = sub_bbox[0]  # 副标题左侧偏移
            sub_color = tuple(int(c * 0.85) for c in title_color)
            draw.text((x, y + text_h + 50), subtitle, font=sub_font, fill=sub_color + (255,))
        
        return canvas.convert("RGB")


# ========== 风格3：极简九宫格 ==========

class Style3Grid(BaseStyle):
    """风格3：极简九宫格 - 整列旋转"""
    
    id = "style3"
    name = "九宫格"
    description = "整列旋转倾斜排列"
    is_animated = False
    
    def generate(self, images: List[Image.Image]) -> Image.Image:
        width, height = 1920, 1080
        title = self.params.get("title", "媒体库")
        subtitle = self.params.get("subtitle", "")
        
        # 背景配置
        bg_mode = self.params.get("bg_mode", "auto")
        bg_preset = self.params.get("bg_preset", 0)
        bg_custom = self.params.get("bg_custom", None)
        
        preset_colors = [
            (66, 133, 244), (234, 67, 53), (251, 188, 5), (52, 168, 83),
            (156, 39, 176), (255, 152, 0), (0, 188, 212), (233, 30, 99),
        ]
        
        if bg_mode == "custom" and bg_custom:
            main_color = tuple(bg_custom)
        elif bg_mode == "preset":
            main_color = preset_colors[bg_preset % len(preset_colors)]
        elif bg_mode == "random":
            main_color = random.choice(preset_colors)
        else:
            main_color = extract_color(images[0])
        
        # MoviePilot 参数
        MARGIN = 22
        CORNER_RADIUS = 46
        ROTATION_ANGLE = -15.8
        START_X = 835
        START_Y = -362
        CELL_WIDTH = 410
        CELL_HEIGHT = 610
        
        while len(images) < 8:
            images = images + images
        images = images[:8]
        
        # === 渐变背景 ===
        canvas = Image.new("RGB", (width, height), main_color)
        
        color_dark = darken(main_color, 0.4)
        color_light = lighten(main_color, 1.2)
        left_end = int(width * 0.4)
        
        for x in range(left_end):
            ratio = x / left_end
            r = int(color_dark[0] * (1 - ratio) + color_light[0] * ratio)
            g = int(color_dark[1] * (1 - ratio) + color_light[1] * ratio)
            b = int(color_dark[2] * (1 - ratio) + color_light[2] * ratio)
            draw_line = ImageDraw.Draw(canvas)
            draw_line.line([(x, 0), (x, height)], fill=(r, g, b))
        
        for x in range(left_end, width):
            ratio = (x - left_end) / (width - left_end)
            r = int(color_light[0] * (1 - ratio * 0.3))
            g = int(color_light[1] * (1 - ratio * 0.3))
            b = int(color_light[2] * (1 - ratio * 0.3))
            draw_line = ImageDraw.Draw(canvas)
            draw_line.line([(x, 0), (x, height)], fill=(r, g, b))
        
        canvas = canvas.convert("RGBA")

        # 背景色用于标题颜色计算
        bg_color = color_light
        
        # === 按列分组：3+3+2 ===
        grouped_posters = [
            images[0:3],   # 第1列：3张
            images[3:6],   # 第2列：3张
            images[6:8],   # 第3列：2张
        ]
        
        # === 逐列处理 ===
        for col_index, column_images in enumerate(grouped_posters):
            num_posters = len(column_images)
            column_height = num_posters * CELL_HEIGHT + (num_posters - 1) * MARGIN
            
            # 创建列画布
            column_image = Image.new("RGBA", (CELL_WIDTH, column_height), (0, 0, 0, 0))
            
            # 粘贴海报
            for row_index, img in enumerate(column_images):
                poster = ImageOps.fit(img.convert("RGB"), (CELL_WIDTH, CELL_HEIGHT), Image.LANCZOS)
                
                # 圆角
                mask = Image.new("L", (CELL_WIDTH, CELL_HEIGHT), 0)
                ImageDraw.Draw(mask).rounded_rectangle(
                    [(0, 0), (CELL_WIDTH, CELL_HEIGHT)], radius=CORNER_RADIUS, fill=255)
                poster_rgba = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
                poster_rgba.paste(poster, (0, 0))
                poster_rgba.putalpha(mask)
                poster = poster_rgba
                
                # 投影
                shadow = Image.new("RGBA", (CELL_WIDTH + 20, CELL_HEIGHT + 20), (0, 0, 0, 0))
                shadow_layer = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 80))
                shadow_mask = Image.new('L', (CELL_WIDTH, CELL_HEIGHT), 0)
                ImageDraw.Draw(shadow_mask).rounded_rectangle(
                    [(0, 0), (CELL_WIDTH, CELL_HEIGHT)], radius=CORNER_RADIUS, fill=255)
                shadow_layer.putalpha(shadow_mask)
                shadow.paste(shadow_layer, (10, 10))
                shadow = shadow.filter(ImageFilter.GaussianBlur(10))
                shadow.paste(poster, (5, 5), poster)
                
                y_pos = row_index * (CELL_HEIGHT + MARGIN)
                column_image.paste(shadow, (0, y_pos), shadow)
            
            # === 旋转整列 ===
            rotation_size = int(math.sqrt(CELL_WIDTH**2 + column_height**2) * 1.5)
            rotation_canvas = Image.new("RGBA", (rotation_size, rotation_size), (0, 0, 0, 0))
            paste_x = (rotation_size - CELL_WIDTH) // 2
            paste_y = (rotation_size - column_height) // 2
            rotation_canvas.paste(column_image, (paste_x, paste_y), column_image)
            rotated_column = rotation_canvas.rotate(ROTATION_ANGLE, Image.BICUBIC, expand=True)
            
            # === 计算位置 ===
            col_spacing = CELL_WIDTH + 80  # 490
            
            if col_index == 0:
                column_center_x = START_X
            elif col_index == 1:
                column_center_x = START_X + col_spacing
            else:
                column_center_x = START_X + col_spacing * 2
            
            full_column_height = 3 * CELL_HEIGHT + 2 * MARGIN
            base_center_y = START_Y + full_column_height // 2
            
            if col_index == 2 and num_posters < 3:
                column_center_y = base_center_y - 155 + 150
            else:
                column_center_y = START_Y + column_height // 2
            
            final_x = int(column_center_x - rotated_column.width // 2 + CELL_WIDTH // 2)
            final_y = int(column_center_y - rotated_column.height // 2)
            
            canvas.paste(rotated_column, (final_x, final_y), rotated_column)
        
        
        # === 标题 ===
        draw = ImageDraw.Draw(canvas)
        
        # 获取字体大小模板
        font_size_mode = self.params.get("font_size_mode", "medium")
        font_size, sub_font_size, line_width = get_font_size(title, font_size_mode)
        font = get_font(font_size)
        
        bbox = font.getbbox(title)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        title_x = int(width * 0.08)
        title_y = height // 2 - text_h // 2 - 30
        
        # 获取标题颜色
        title_color = get_title_color(self.params, bg_color)
        
        # 横线
        line_w = min(text_w, line_width)
        draw.rectangle([(title_x, title_y - 20), (title_x + line_w, title_y - 14)], fill=title_color + (255,))
        
        draw.text((title_x, title_y), title, font=font, fill=title_color + (255,))
        
        if subtitle:
            sub_font = get_font(sub_font_size)
            sub_color = tuple(int(c * 0.85) for c in title_color)
            draw.text((title_x, title_y + text_h + 50), subtitle, font=sub_font, fill=sub_color + (220,))
        
        return canvas.convert("RGB")


# ========== 风格4：极简封面 ==========

class Style4Minimal(BaseStyle):
    id = "style4"
    name = "极简封面"
    description = "横版背景+底部5张海报"
    is_animated = False
    
    def generate(self, images: List[Image.Image]) -> Image.Image:
        width, height = 1920, 1080
        title = self.params.get("title", "媒体库")
        subtitle = self.params.get("subtitle", "")
        
        # 背景配置
        bg_mode = self.params.get("bg_mode", "auto")
        bg_preset = self.params.get("bg_preset", 0)
        bg_custom = self.params.get("bg_custom", None)
        
        # 标题颜色配置
        title_color_mode = self.params.get("title_color_mode", "white")  # white/black/auto/custom
        title_color_custom = self.params.get("title_color_custom", [255, 255, 255])
        
        preset_colors = [
            (66, 133, 244), (234, 67, 53), (251, 188, 5), (52, 168, 83),
            (156, 39, 176), (255, 152, 0), (0, 188, 212), (233, 30, 99),
        ]
        
        if not images:
            raise ValueError("需要图片")
        
        # 需要6张图片：1张横版背景 + 5张竖版海报
        while len(images) < 6:
            images = images + images
        images = images[:6]
        
        # 确定背景颜色
        if bg_mode == "custom" and bg_custom:
            main_color = tuple(bg_custom)
        elif bg_mode == "preset":
            main_color = preset_colors[bg_preset % len(preset_colors)]
        elif bg_mode == "random":
            main_color = random.choice(preset_colors)
        else:
            main_color = extract_color(images[0])
        
        bg_color = darken(main_color, 0.3)
        
        canvas = Image.new("RGB", (width, height), bg_color)
        
        # 1. 横版封面作为背景（铺满整个海报）
        bg_img = ImageOps.fit(images[0].convert("RGB"), (width, height), Image.LANCZOS)
        canvas.paste(bg_img, (0, 0))
        
        canvas = canvas.convert("RGBA")
        
        # 添加暗色遮罩让标题和海报更清晰
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        # 上半部分渐变遮罩（标题区域）
        for y in range(int(height * 0.4)):
            alpha = int(120 * (1 - y / (height * 0.4)))
            for x in range(width):
                overlay.putpixel((x, y), (0, 0, 0, alpha))
        # 下半部分遮罩（海报区域）
        for y in range(int(height * 0.55), height):
            alpha = int(160 * ((y - height * 0.55) / (height * 0.45)))
            for x in range(width):
                overlay.putpixel((x, y), (0, 0, 0, alpha))
        canvas = Image.alpha_composite(canvas, overlay)
        
        # 2. 底部5张竖版海报
        poster_w, poster_h = 336, 504  # 竖版海报尺寸（再放大20%）
        poster_y = height - poster_h - 40  # 距底部40px
        poster_spacing = 30  # 海报间距
        total_width = 5 * poster_w + 4 * poster_spacing
        start_x = (width - total_width) // 2  # 居中
        
        for i in range(5):
            img = images[i + 1].convert("RGB") if i + 1 < len(images) else images[1].convert("RGB")
            poster = ImageOps.fit(img, (poster_w, poster_h), Image.LANCZOS)
            
            # 圆角
            mask = Image.new('L', (poster_w, poster_h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (poster_w, poster_h)], radius=16, fill=255)
            poster_rgba = Image.new("RGBA", (poster_w, poster_h), (0, 0, 0, 0))
            poster_rgba.paste(poster, (0, 0))
            poster_rgba.putalpha(mask)
            
            # 阴影
            shadow = Image.new("RGBA", (poster_w + 20, poster_h + 20), (0, 0, 0, 0))
            shadow_layer = Image.new("RGBA", (poster_w, poster_h), (0, 0, 0, 60))
            shadow_mask = Image.new('L', (poster_w, poster_h), 0)
            ImageDraw.Draw(shadow_mask).rounded_rectangle([(0, 0), (poster_w, poster_h)], radius=16, fill=255)
            shadow_layer.putalpha(shadow_mask)
            shadow.paste(shadow_layer, (10, 10))
            shadow = shadow.filter(ImageFilter.GaussianBlur(12))
            shadow.paste(poster_rgba, (5, 5), poster_rgba)
            
            pos_x = start_x + i * (poster_w + poster_spacing)
            canvas.paste(shadow, (pos_x, poster_y), shadow)
        
        # 3. 左上角：横线、标题、副标题
        draw = ImageDraw.Draw(canvas)
        
        # 确定标题颜色
        if title_color_mode == "black":
            title_color = (0, 0, 0)
        elif title_color_mode == "custom":
            title_color = tuple(title_color_custom)
        elif title_color_mode == "auto":
            # 根据背景亮度自动选择
            brightness = sum(main_color) / 3
            title_color = (0, 0, 0) if brightness > 128 else (255, 255, 255)
        else:  # white
            title_color = (255, 255, 255)
        
        # 获取字体大小模板
        font_size_mode = self.params.get("font_size_mode", "medium")
        font_size, sub_font_size, line_width = get_font_size(title, font_size_mode)
        font = get_font(font_size)
        
        bbox = font.getbbox(title)
        text_h = bbox[3] - bbox[1]
        
        x = 80
        y = 80
        
        # 横线（使用标题颜色）
        draw.rectangle([(x, y), (x + line_width, y + 6)], fill=title_color + (255,))
        
        # 主标题
        draw.text((x, y + 40), title, font=font, fill=title_color + (255,))
        
        # 副标题（稍暗）
        if subtitle:
            sub_font = get_font(sub_font_size)
            sub_color = tuple(int(c * 0.9) for c in title_color)
            draw.text((x, y + text_h + 80), subtitle, font=sub_font, fill=sub_color + (255,))
        
        return canvas.convert("RGB")


# ========== 注册 ==========

STATIC_STYLES = {
    "style1": Style1CardStack,
    "style2": Style2Diagonal,
    "style3": Style3Grid,
    "style4": Style4Minimal,
}


def get_static_style(style_id: str, params: Optional[Dict[str, Any]] = None) -> BaseStyle:
    if style_id not in STATIC_STYLES:
        raise ValueError(f"未知风格: {style_id}")
    return STATIC_STYLES[style_id](params)


def list_static_styles() -> List[Dict[str, Any]]:
    return [
        {"id": s.id, "name": s.name, "description": s.description, "is_animated": False}
        for s in STATIC_STYLES.values()
    ]




