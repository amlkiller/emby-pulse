from .base import BaseStyle
from .static import get_static_style, list_static_styles, STATIC_STYLES
from typing import Dict, Any, List


def get_style(style_id: str, params: Dict[str, Any] = None):
    """获取风格实例"""
    return get_static_style(style_id, params)


def list_all_styles() -> List[Dict[str, Any]]:
    """列出所有风格"""
    return list_static_styles()
