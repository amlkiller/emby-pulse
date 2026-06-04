# -*- coding: utf-8 -*-
"""
图像内容校验工具。

用于头像等"用户上传 base64 图片"场景：仅依赖 data:image MIME 前缀
不足以防止伪造，必须解码后用 magic bytes + PIL 二次解析校验真实内容。

参考实现：app/routers/pwa.py 中 PWA 图标上传的校验范式。
"""

import base64
from io import BytesIO


_ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}
_MIME_BY_FORMAT = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
    "GIF": "image/gif",
}


def check_magic_bytes(content: bytes) -> bool:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if content.startswith(b"\xff\xd8\xff"):
        return True
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return True
    if content.startswith(b"GIF87a") or content.startswith(b"GIF89a"):
        return True
    return False


def validate_image_bytes(content: bytes, max_bytes: int = 2 * 1024 * 1024) -> tuple[bytes, str]:
    """校验并重写原始图片字节。

    Returns:
        ``(rebuilt_bytes, mime_type)``，其中 MIME 来自 PIL 解析出的真实格式。

    Raises:
        ValueError: 校验失败（超限 / 非图片 / 格式不允许）
    """
    if len(content) > max_bytes:
        raise ValueError(f"头像不能超过 {max_bytes // 1024} KB")

    if not check_magic_bytes(content):
        raise ValueError("头像文件头校验失败，疑似伪造")

    try:
        from PIL import Image
    except ImportError:
        raise ValueError("服务端缺少图像处理库")

    try:
        img = Image.open(BytesIO(content))
        img.verify()
    except Exception:
        raise ValueError("头像解析失败")

    img = Image.open(BytesIO(content))
    fmt = (img.format or "").upper()
    if fmt not in _ALLOWED_FORMATS:
        raise ValueError(f"不支持的图片格式：{fmt or '未知'}")

    out = BytesIO()
    save_kwargs = {"format": fmt}
    if fmt == "JPEG":
        save_kwargs["quality"] = 90
        save_kwargs["optimize"] = True
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
    elif fmt == "PNG":
        save_kwargs["optimize"] = True
    img.save(out, **save_kwargs)

    return out.getvalue(), _MIME_BY_FORMAT[fmt]


def validate_base64_image(data_url: str, max_bytes: int = 2 * 1024 * 1024) -> str:
    """校验并重写 base64 头像数据。

    - 仅接受 ``data:image/<png|jpeg|webp|gif>;base64,...`` 形式
    - 解码后大小 ≤ ``max_bytes``
    - magic bytes 与 PIL 二次解析双重校验
    - 重新编码（剥离 EXIF 等元数据），返回安全的新 data URL

    Args:
        data_url: 原始 base64 data URL
        max_bytes: 解码后字节数上限

    Returns:
        重新编码后的 data URL 字符串

    Raises:
        ValueError: 校验失败（前缀错误 / 解码失败 / 超限 / 非图片 / 格式不允许）
    """
    if not isinstance(data_url, str) or not data_url.startswith("data:image/"):
        raise ValueError("头像必须为 data:image/* 格式")

    try:
        header, payload = data_url.split(",", 1)
    except ValueError:
        raise ValueError("头像格式不正确")

    if ";base64" not in header:
        raise ValueError("头像必须为 base64 编码")

    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception:
        raise ValueError("头像 base64 解码失败")

    rebuilt, mime = validate_image_bytes(raw, max_bytes=max_bytes)
    new_b64 = base64.b64encode(rebuilt).decode("ascii")
    return f"data:{mime};base64,{new_b64}"
