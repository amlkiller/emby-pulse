"""风格生成器基类"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from PIL import Image


class BaseStyle(ABC):
    """风格基类"""
    
    id: str = "base"
    name: str = "基础风格"
    description: str = ""
    is_animated: bool = False
    
    # 默认参数
    default_params: Dict[str, Any] = {
        "width": 1920,
        "height": 1080,
        "title": "",
        "subtitle": "",
        "font_size": 72,
        "subtitle_size": 36,
        "text_color": (255, 255, 255),
        "bg_color": (20, 20, 20),
    }
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        self.params = {**self.default_params, **(params or {})}
    
    @abstractmethod
    def generate(self, images: List[Image.Image]) -> Image.Image:
        """
        生成封面
        
        Args:
            images: 图片列表
        
        Returns:
            生成的封面图片
        """
        pass
    
    def get_params_schema(self) -> List[Dict[str, Any]]:
        """获取参数配置项"""
        return [
            {"key": "title", "label": "主标题", "type": "text", "default": ""},
            {"key": "subtitle", "label": "副标题", "type": "text", "default": ""},
            {"key": "font_size", "label": "主标题字号", "type": "number", "default": 72},
            {"key": "subtitle_size", "label": "副标题字号", "type": "number", "default": 36},
        ]
    
    def validate_images(self, images: List[Image.Image], min_count: int = 1) -> bool:
        """验证图片数量"""
        return len(images) >= min_count
    
    def ensure_image_count(self, images: List[Image.Image], count: int) -> List[Image.Image]:
        """确保图片数量足够"""
        if len(images) >= count:
            return images[:count]
        
        # 重复填充
        result = images.copy()
        while len(result) < count:
            result.extend(images)
        return result[:count]
