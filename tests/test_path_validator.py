# -*- coding: utf-8 -*-
"""
路径与文件名安全工具单元测试。
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.path_validator import safe_filename, safe_join


def test_safe_filename_strips_directories():
    assert safe_filename("../etc/passwd") == "passwd"
    assert safe_filename("..\\..\\windows\\system32.dll") == "system32.dll"


def test_safe_filename_strips_unsafe_chars():
    assert safe_filename("hello world.png") == "helloworld.png"
    assert safe_filename("a$b%c.jpg") == "abc.jpg"


def test_safe_filename_rejects_dot_only():
    assert safe_filename("..", fallback="x") == "x"
    assert safe_filename(".", fallback="x") == "x"
    assert safe_filename("...", fallback="x") == "x"  # 全是点会被 lstrip 干掉


def test_safe_filename_empty_uses_fallback():
    assert safe_filename("", fallback="default") == "default"
    assert safe_filename("///", fallback="default") == "default"


def test_safe_filename_truncates_long_names():
    name = "a" * 300 + ".png"
    assert len(safe_filename(name)) == 200


def test_safe_join_within_base():
    with tempfile.TemporaryDirectory() as base:
        result = safe_join(base, "child.txt")
        assert str(result).startswith(os.path.realpath(base))


def test_safe_join_rejects_parent_escape():
    with tempfile.TemporaryDirectory() as base:
        with pytest.raises(ValueError):
            safe_join(base, "../../etc/passwd")


def test_safe_join_rejects_absolute_path():
    with tempfile.TemporaryDirectory() as base:
        abs_path = "C:/Windows/system32.dll" if os.name == "nt" else "/etc/passwd"
        with pytest.raises(ValueError):
            safe_join(base, abs_path)


def test_safe_join_rejects_empty():
    with tempfile.TemporaryDirectory() as base:
        with pytest.raises(ValueError):
            safe_join(base, "")
