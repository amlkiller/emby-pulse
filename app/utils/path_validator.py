# -*- coding: utf-8 -*-
"""
路径与文件名安全工具。

用于未来扩展到"磁盘上传"场景时建立护栏：拒绝路径穿越、绝对路径、
符号链接逃逸等常见手法。当前头像走 base64 入库，无路径风险，但
该工具应在新增任何 ``UploadFile`` 写盘端点时被强制调用。
"""

import os
import re
from pathlib import Path


_UNSAFE_FILENAME_CHARS = re.compile(r"[^a-zA-Z0-9._\-]")


def safe_filename(name: str, fallback: str = "file") -> str:
    """清洗用户提供的文件名，仅保留 ``[a-zA-Z0-9._-]``，并阻断隐藏文件。

    - 去掉路径分隔符与所有非白名单字符
    - 拒绝纯 ``.`` 或 ``..``
    - 空结果回退到 ``fallback``
    - 限长 200，避免文件系统限制问题
    """
    if not isinstance(name, str):
        return fallback
    # 仅取末段，剥离任何客户端给的目录结构
    base = os.path.basename(name.replace("\\", "/"))
    cleaned = _UNSAFE_FILENAME_CHARS.sub("", base).lstrip(".")
    if not cleaned or cleaned in {".", ".."}:
        return fallback
    return cleaned[:200]


def safe_join(base_dir, user_input: str) -> Path:
    """把用户输入的相对路径拼到 ``base_dir`` 之内，禁止逃逸。

    Args:
        base_dir: 允许写入的根目录（必须已存在或可创建）
        user_input: 用户提供的相对路径片段（建议先经过 safe_filename）

    Returns:
        ``base_dir`` 子树内的绝对 Path。

    Raises:
        ValueError: 拼接结果超出 base_dir（路径穿越 / 绝对路径 / 符号链接逃逸）。
    """
    if not isinstance(user_input, str) or not user_input:
        raise ValueError("路径不能为空")

    base = Path(base_dir).resolve()
    candidate = (base / user_input).resolve()

    try:
        candidate.relative_to(base)
    except ValueError:
        raise ValueError("路径越界，禁止访问 base 目录之外的位置")

    return candidate
