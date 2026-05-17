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
    """
    Sanitize rich text HTML from Quill editor
    Allows safe HTML tags while removing dangerous content
    
    Args:
        text: Input HTML text to sanitize
        max_length: Maximum allowed length (default 50000)
    
    Returns:
        Sanitized HTML safe for storage and display
    """
    if not text:
        return ""
    
    text = str(text)
    
    # Truncate to max length
    if len(text) > max_length:
        text = text[:max_length]
    
    # First decode any HTML entities to get raw HTML
    text = html.unescape(text)
    
    # Remove dangerous patterns
    dangerous_patterns = [
        r'javascript\s*:',
        r'vbscript\s*:',
        r'data\s*:\s*text/html',
    ]
    
    for pattern in dangerous_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Remove all event handlers (onclick, onload, onerror, etc.)
    text = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+on\w+\s*=\s*[^\s>]+', '', text, flags=re.IGNORECASE)
    
    # Remove script and style tags completely
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<script[^>]*/?>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<style[^>]*/?>', '', text, flags=re.IGNORECASE)
    
    # Remove iframe, embed, object tags
    text = re.sub(r'<iframe[^>]*>.*?</iframe>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<embed[^>]*/?>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<object[^>]*>.*?</object>', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Remove form tags
    text = re.sub(r'<form[^>]*>.*?</form>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<input[^>]*/?>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'<button[^>]*>.*?</button>', '', text, flags=re.IGNORECASE | re.DOTALL)
    
    # Clean href attributes - only allow safe protocols
    def clean_href(match):
        href = match.group(1)
        # Check for dangerous protocols
        href_lower = href.lower().strip()
        if href_lower.startswith(('javascript:', 'vbscript:', 'data:')):
            return 'href="#"'
        return f'href="{href}"'
    
    text = re.sub(r'href\s*=\s*["\']([^"\']*)["\']', clean_href, text, flags=re.IGNORECASE)
    
    # Clean src attributes - only allow safe protocols
    def clean_src(match):
        src = match.group(1)
        src_lower = src.lower().strip()
        if src_lower.startswith(('javascript:', 'vbscript:')):
            return 'src="#"'
        return f'src="{src}"'
    
    text = re.sub(r'src\s*=\s*["\']([^"\']*)["\']', clean_src, text, flags=re.IGNORECASE)
    
    # Fix unclosed tags
    try:
        text = fix_unclosed_html_tags(text)
    except Exception:
        pass  # If fixing fails, return as is
    
    return text


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
