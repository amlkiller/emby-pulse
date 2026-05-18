# -*- coding: utf-8 -*-
"""
Security utilities for input sanitization
"""

import html
import re
from html.parser import HTMLParser


def sanitize_html(text: str, max_length: int = 500) -> str:
    """
    Sanitize user input to prevent XSS attacks
    
    Args:
        text: Input text to sanitize
        max_length: Maximum allowed length (default 500)
    
    Returns:
        Sanitized text safe for storage and display
    """
    if not text:
        return ""
    
    # Convert to string
    text = str(text)
    
    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length]
    
    # HTML escape
    text = html.escape(text, quote=True)
    
    # Remove potentially dangerous patterns
    dangerous_patterns = [
        r'javascript:',
        r'on\w+\s*=',  # Event handlers like onclick=
        r'data:text/html',
        r'vbscript:',
    ]
    
    for pattern in dangerous_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    return text


def sanitize_sql(text: str) -> str:
    """
    Additional SQL sanitization for user inputs
    Note: Always use parameterized queries instead of string concatenation
    
    Args:
        text: Input text to sanitize
    
    Returns:
        Sanitized text
    """
    if not text:
        return ""
    
    text = str(text)
    
    # Remove null bytes
    text = text.replace('\x00', '')
    
    # Remove control characters
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    
    return text


def is_safe_redirect(url: str, allowed_hosts: list = None) -> bool:
    """
    Check if a redirect URL is safe (prevents open redirect attacks)
    
    Args:
        url: URL to check
        allowed_hosts: List of allowed hostnames
    
    Returns:
        True if safe, False otherwise
    """
    if not url:
        return False
    
    # Relative URLs are safe
    if url.startswith('/') and not url.startswith('//'):
        return True
    
    # Check for allowed hosts
    if allowed_hosts:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            return parsed.hostname in allowed_hosts
        except:
            return False
    
    return False


def validate_redirect_url(url: str) -> str:
    """
    Validate and sanitize redirect URL
    
    Args:
        url: URL to validate
    
    Returns:
        Safe URL or empty string if invalid
    """
    if not url:
        return ""
    
    # Only allow http/https protocols
    if not url.startswith(('http://', 'https://')):
        return ""
    
    # Block javascript: and data: protocols
    lower_url = url.lower()
    if lower_url.startswith(('javascript:', 'data:', 'vbscript:')):
        return ""
    
    return url


def sanitize_rich_html(text: str, max_length: int = 50000) -> str:
    if not text:
        return ""
    text = str(text)
    if len(text) > max_length:
        text = text[:max_length]
    try:
        import bleach
        allowed_tags = [
            'p', 'br', 'strong', 'em', 'u', 's', 'a', 'ul', 'ol', 'li',
            'blockquote', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'img', 'span', 'div', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
            'hr', 'sub', 'sup', 'mark',
        ]
        allowed_attrs = {
            'a': ['href', 'title', 'target'],
            'img': ['src', 'alt', 'width', 'height'],
            'span': ['style'],
            'div': ['style'],
            'td': ['colspan', 'rowspan'],
            'th': ['colspan', 'rowspan'],
        }
        return bleach.clean(
            text,
            tags=allowed_tags,
            attributes=allowed_attrs,
            protocols=['http', 'https', 'mailto'],
            strip=True,
        )
    except ImportError:
        # bleach 未安装时降级到基本转义
        import html as _html
        return _html.escape(text)


def fix_unclosed_html_tags(text: str) -> str:
    """
    Fix unclosed HTML tags by properly parsing and reconstructing the HTML.
    Uses a stack-based approach to close any unclosed tags.
    """
    # Self-closing tags that don't need closing
    self_closing = {'br', 'hr', 'img', 'input', 'meta', 'link', 'area', 'base', 'col', 'embed', 'param', 'source', 'track', 'wbr'}
    
    # Stack to track open tags
    open_tags = []
    result = []
    pos = 0
    
    # Regex to find tags
    tag_pattern = re.compile(r'<(/?)(\w+)([^>]*)>', re.IGNORECASE)
    
    for match in tag_pattern.finditer(text):
        # Add text before this tag
        result.append(text[pos:match.start()])
        pos = match.end()
        
        is_closing = match.group(1) == '/'
        tag_name = match.group(2).lower()
        attrs = match.group(3)
        
        # Skip self-closing tags
        if tag_name in self_closing:
            result.append(match.group(0))
            continue
        
        # Check if it's a self-closing tag with />
        if attrs.strip().endswith('/'):
            result.append(match.group(0))
            continue
        
        if is_closing:
            # Closing tag
            if open_tags and open_tags[-1] == tag_name:
                open_tags.pop()
                result.append(match.group(0))
            elif tag_name in open_tags:
                # Close all tags up to this one
                while open_tags and open_tags[-1] != tag_name:
                    unclosed = open_tags.pop()
                    result.append(f'</{unclosed}>')
                if open_tags:
                    open_tags.pop()
                    result.append(match.group(0))
            else:
                # Orphan closing tag, just include it
                result.append(match.group(0))
        else:
            # Opening tag
            open_tags.append(tag_name)
            result.append(match.group(0))
    
    # Add remaining text
    result.append(text[pos:])
    
    # Close any remaining open tags
    while open_tags:
        tag = open_tags.pop()
        result.append(f'</{tag}>')
    
    return ''.join(result)


def safe_error_message(error: Exception, default_msg: str = "操作失败") -> str:
    """
    Generate safe error message that doesn't expose internal details

    Args:
        error: Exception object
        default_msg: Default message to return

    Returns:
        Safe error message for user display
    """
    # Log the actual error for debugging
    import logging
    logger = logging.getLogger("uvicorn")
    logger.error(f"[Security] Internal error: {str(error)}")

    # Return generic message to user
    return default_msg


def safe_http_exception(status_code: int, default_msg: str, error: Exception = None):
    """构造 HTTPException，记录原始异常但只返回通用文案。

    Args:
        status_code: HTTP 状态码
        default_msg: 面向客户端的通用消息
        error: 内部异常对象（可选），仅写入服务端日志

    Returns:
        fastapi.HTTPException 实例（调用方 raise 即可）
    """
    from fastapi import HTTPException
    import logging
    logger = logging.getLogger("uvicorn")
    if error is not None:
        logger.exception(f"[Security] HTTP {status_code}: {default_msg} - {error!r}")
    return HTTPException(status_code=status_code, detail=default_msg)
