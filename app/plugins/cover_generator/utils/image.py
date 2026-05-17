"""图片处理工具"""
import io
import logging
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
from typing import List, Tuple, Optional

logger = logging.getLogger("uvicorn")


def load_image_from_bytes(data: bytes) -> Optional[Image.Image]:
    """从字节数据加载图片"""
    try:
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as e:
        logger.error(f"加载图片失败: {e}")
        return None


def resize_image(img: Image.Image, size: Tuple[int, int], keep_ratio: bool = True) -> Image.Image:
    """调整图片大小"""
    if keep_ratio:
        img.thumbnail(size, Image.LANCZOS)
        # 创建画布并居中
        canvas = Image.new("RGB", size, (20, 20, 20))
        x = (size[0] - img.width) // 2
        y = (size[1] - img.height) // 2
        canvas.paste(img, (x, y))
        return canvas
    else:
        return img.resize(size, Image.LANCZOS)


def crop_center(img: Image.Image, size: Tuple[int, int]) -> Image.Image:
    """从中心裁剪图片"""
    w, h = img.size
    target_w, target_h = size
    
    # 计算裁剪区域
    ratio = max(target_w / w, target_h / h)
    new_w = int(w * ratio)
    new_h = int(h * ratio)
    
    img = img.resize((new_w, new_h), Image.LANCZOS)
    
    # 居中裁剪
    x = (new_w - target_w) // 2
    y = (new_h - target_h) // 2
    
    return img.crop((x, y, x + target_w, y + target_h))


def create_blur_background(img: Image.Image, size: Tuple[int, int], blur: int = 30) -> Image.Image:
    """创建模糊背景"""
    # 缩放到目标尺寸
    bg = img.resize(size, Image.LANCZOS)
    # 高斯模糊
    bg = bg.filter(ImageFilter.GaussianBlur(blur))
    # 降低亮度
    enhancer = ImageEnhance.Brightness(bg)
    bg = enhancer.enhance(0.6)
    return bg


def add_gradient_overlay(img: Image.Image, direction: str = "bottom") -> Image.Image:
    """添加渐变遮罩"""
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    if direction == "bottom":
        for y in range(h):
            alpha = int(255 * (y / h) ** 1.5)
            draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    elif direction == "top":
        for y in range(h):
            alpha = int(255 * (1 - y / h) ** 1.5)
            draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    elif direction == "both":
        for y in range(h // 2):
            alpha = int(255 * (y / (h // 2)) ** 1.5)
            draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
            draw.line([(0, h - 1 - y), (w, h - 1 - y)], fill=(0, 0, 0, alpha))
    
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    
    return Image.alpha_composite(img, overlay)


def draw_text_with_shadow(draw: ImageDraw.ImageDraw, pos: Tuple[int, int], 
                          text: str, font, fill: Tuple[int, int, int] = (255, 255, 255),
                          shadow: bool = True, shadow_color: Tuple[int, int, int] = (0, 0, 0),
                          shadow_offset: int = 3):
    """绘制带阴影的文字"""
    x, y = pos
    if shadow:
        # 绘制阴影
        for dx in range(-shadow_offset, shadow_offset + 1):
            for dy in range(-shadow_offset, shadow_offset + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text, font=font, fill=shadow_color)
    # 绘制文字
    draw.text(pos, text, font=font, fill=fill)


def create_rounded_mask(size: Tuple[int, int], radius: int) -> Image.Image:
    """创建圆角遮罩"""
    w, h = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (w, h)], radius=radius, fill=255)
    return mask


def apply_rounded_corners(img: Image.Image, radius: int) -> Image.Image:
    """应用圆角"""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    mask = create_rounded_mask(img.size, radius)
    img.putalpha(mask)
    return img


def create_grid(images: List[Image.Image], cols: int, rows: int, 
                size: Tuple[int, int], gap: int = 4, 
                bg_color: Tuple[int, int, int] = (20, 20, 20)) -> Image.Image:
    """创建图片网格"""
    canvas = Image.new("RGB", size, bg_color)
    
    cell_w = (size[0] - gap * (cols + 1)) // cols
    cell_h = (size[1] - gap * (rows + 1)) // rows
    
    for i, img in enumerate(images[:cols * rows]):
        row = i // cols
        col = i % cols
        
        # 裁剪并调整大小
        cell_img = crop_center(img, (cell_w, cell_h))
        
        # 计算位置
        x = gap + col * (cell_w + gap)
        y = gap + row * (cell_h + gap)
        
        canvas.paste(cell_img, (x, y))
    
    return canvas


def blend_images(images: List[Image.Image], weights: Optional[List[float]] = None) -> Image.Image:
    """混合多张图片"""
    if not images:
        raise ValueError("没有图片可混合")
    
    if weights is None:
        weights = [1.0 / len(images)] * len(images)
    
    # 确保所有图片大小一致
    size = images[0].size
    result = Image.new("RGB", size, (0, 0, 0))
    
    for img, weight in zip(images, weights):
        if img.size != size:
            img = img.resize(size, Image.LANCZOS)
        
        # 加权混合
        pixels = img.load()
        result_pixels = result.load()
        
        for x in range(size[0]):
            for y in range(size[1]):
                r, g, b = pixels[x, y]
                rr, rg, rb = result_pixels[x, y]
                result_pixels[x, y] = (
                    int(rr + r * weight),
                    int(rg + g * weight),
                    int(rb + b * weight)
                )
    
    return result
