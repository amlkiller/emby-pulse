"""
影巢签到插件
功能：
- 自动完成影巢(HDHive)每日签到
- 支持普通签到和赌狗签到两种模式
- 支持签到失败重试
- 保存签到历史记录
- 支持用户名密码自动登录刷新Cookie
- 支持签到通知推送到管理机器人
- 支持动态获取 next-action 值
"""
import time
import re
import json
import base64
import logging
import threading
import datetime
import requests
from typing import Optional, Dict, Tuple, Any, List
from fastapi import Request
from app.plugins.base import PluginBase
from app.core.config import cfg
from app.core.event_bus import bus

logger = logging.getLogger("uvicorn")

# 影巢站点配置
HDHIVE_BASE = "https://hdhive.com"


def decode_jwt_payload(token: str) -> dict:
    """解码 JWT token 的 payload 部分（⚠️ 不验证签名，仅用于读取非敏感 claims）"""
    try:
        # JWT 格式: header.payload.signature
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        
        # 解码 payload 部分
        payload = parts[1]
        # 添加 padding
        padding = len(payload) % 4
        if padding:
            payload += '=' * (4 - padding)
        
        # Base64 解码
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        logger.debug(f"[影巢签到] JWT 解码失败: {e}")
        return {}


class HDHiveSignPlugin(PluginBase):
    """影巢签到插件"""
    
    id = "hdhivesign"
    name = "影巢签到"
    description = "影巢每日自动签到，支持普通/赌狗模式，自动登录刷新Cookie（Pro 专享）"
    icon = "fa-calendar-check"
    icon_color = "from-purple-500 to-pink-500"
    version = "1.0.1"
    author = "EmbyPulse"
    pro_only = True  # 仅 Pro 用户可用
    
    def __init__(self):
        super().__init__()
        self._checkin_thread = None
        self._running = False
        self._last_checkin_date = None
        self._next_action_cache = None
        self._next_action_cache_time = 0
        self._setup_routes()
    
    def on_enable(self):
        """启用插件"""
        self._running = True
        self._checkin_thread = threading.Thread(target=self._checkin_loop, daemon=True)
        self._checkin_thread.start()
        self.log("影巢签到插件已启用", level="info", notify=False)
    
    def on_disable(self):
        """禁用插件"""
        self._running = False
        self.log("影巢签到插件已禁用", level="info", notify=False)
    
    def get_page_url(self):
        """返回插件页面路径"""
        return "/plugins/hdhivesign"

    def get_config_schema(self):
        """返回配置项定义"""
        return [
            {"key": "cookie", "label": "影巢 Cookie", "type": "password",
             "placeholder": "从浏览器复制完整 Cookie",
             "hint": "登录影巢后按 F12 → Network → 任意请求 → Headers → Cookie",
             "default": ""},
            {"key": "username", "label": "用户名/邮箱", "type": "text",
             "placeholder": "用于自动登录刷新 Cookie（可选）",
             "default": ""},
            {"key": "password", "label": "密码", "type": "password",
             "placeholder": "用于自动登录刷新 Cookie（可选）",
             "default": ""},
            {"key": "base_url", "label": "站点地址", "type": "text",
             "placeholder": "https://hdhive.com",
             "hint": "影巢站点地址，支持自定义域名",
             "default": "https://hdhive.com"},
            {"key": "checkin_mode", "label": "签到模式", "type": "select", "options": [
                {"value": "", "label": "请选择签到模式"},
                {"value": "normal", "label": "📅 普通签到（稳定积分）"},
                {"value": "gambler", "label": "🎲 赌狗签到（高风险高回报）"},
            ], "default": ""},
            {"key": "checkin_time", "label": "签到时间", "type": "text",
             "placeholder": "08:00",
             "hint": "每日自动签到时间（北京时间，格式 HH:MM）",
             "default": "08:00"},
            {"key": "notify_bot", "label": "通知管理机器人", "type": "toggle",
             "hint": "签到结果推送到管理机器人（Telegram/企业微信）",
             "default": False},
            {"key": "max_retries", "label": "最大重试次数", "type": "text",
             "placeholder": "3",
             "hint": "签到失败后的重试次数",
             "default": "3"},
            {"key": "retry_interval", "label": "重试间隔(秒)", "type": "text",
             "placeholder": "30",
             "hint": "每次重试的间隔时间",
             "default": "30"},
            {"key": "history_days", "label": "历史保留天数", "type": "text",
             "placeholder": "30",
             "hint": "签到历史记录保留天数",
             "default": "30"},
        ]
    
    def _get_config(self):
        """获取插件配置"""
        from app.plugins import get_plugin_config
        return get_plugin_config(self.id)
    
    def _proxies(self):
        """获取代理配置"""
        proxy = cfg.get("proxy_url")
        return {"http": proxy, "https": proxy} if proxy else None
    
    def _setup_routes(self):
        """注册 API 路由"""
        
        @self.router.get("/status")
        def get_status(request: Request):
            """获取签到状态"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            return self.get_checkin_status()
        
        @self.router.post("/checkin")
        async def do_checkin(request: Request):
            """手动签到"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            try:
                data = await request.json()
                is_gambler = data.get("is_gambler", False)
            except:
                is_gambler = False
            result = self.checkin(is_gambler=is_gambler)
            logger.info(f"[影巢签到] 签到API返回: {result}")
            return result
        
        @self.router.get("/history")
        def get_history(request: Request):
            """获取签到历史"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            limit = int(request.query_params.get("limit", 30))
            return self.get_checkin_history(limit)
        
        @self.router.get("/user")
        def get_user(request: Request):
            """获取用户信息"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            return self.get_user_info()
        
        @self.router.post("/login")
        async def do_login(request: Request):
            """手动登录获取 Cookie"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            try:
                data = await request.json()
                username = data.get("username", "").strip()
                password = data.get("password", "").strip()
                base_url = data.get("base_url", "").strip() or HDHIVE_BASE
            except:
                username = None
                password = None
                base_url = HDHIVE_BASE
            
            return self.test_login(username, password, base_url)
    
    def test_login(self, username: str = None, password: str = None, base_url: str = None) -> dict:
        """测试登录并获取 Cookie"""
        config = self._get_config()
        username = username or config.get("username", "").strip()
        password = password or config.get("password", "").strip()
        base_url = (base_url or config.get("base_url") or HDHIVE_BASE).rstrip("/")
        
        if not username or not password:
            return {"status": "error", "message": "请输入用户名和密码"}
        
        from app.plugins import save_plugin_config
        temp_config = {**config, "username": username, "password": password, "base_url": base_url}
        save_plugin_config(self.id, temp_config)
        
        cookie = self._auto_login()
        
        if cookie:
            save_plugin_config(self.id, {**temp_config, "cookie": cookie})
            cookies = {}
            for item in cookie.split(';'):
                if '=' in item:
                    name, value = item.strip().split('=', 1)
                    cookies[name] = value
            token = cookies.get('token')
            user_info = self._fetch_user_info(cookies, token, base_url) if token else {}
            return {"status": "success", "message": "登录成功", "data": {"cookie": cookie, "user_info": user_info}}
        else:
            return {"status": "error", "message": "登录失败，请检查用户名和密码"}

    # ==========================================
    # 核心签到功能（参考 MoviePilot 插件实现）
    # ==========================================
    
    def _signin_base(self, cookies: dict, token: str, base_url: str, is_gambler: bool = False) -> Tuple[bool, str, int]:
        """执行签到请求
        
        Returns:
            Tuple[bool, str, int]: (是否成功, 消息, 积分变化)
        """
        try:
            # 获取用户ID
            user_id = None
            try:
                decoded = decode_jwt_payload(token)
                user_id = decoded.get('user_id')
            except:
                pass
            
            # 构建请求 URL
            referer = f"{base_url}/" 
            if user_id:
                referer = f"{base_url}/user/{user_id}"
            
            # 动态获取 next-action
            next_action = self._get_next_action_cached(cookies, token, base_url)
            
            # 构建请求头
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/x-component',
                'Accept-Language': 'zh,zh-CN;q=0.9,en;q=0.8',
                'Content-Type': 'text/plain;charset=UTF-8',
                'Origin': base_url,
                'Referer': f'{base_url}/',
                'Next-Action': next_action,
                'Next-Router-State-Tree': '%5B%22%22%2C%7B%22children%22%3A%5B%22(app)%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D',
            }
            csrf_token = cookies.get('csrf_access_token')
            if csrf_token:
                headers['x-csrf-token'] = csrf_token
            
            # 签到数据
            data = '[true]' if is_gambler else '[false]'
            
            logger.info(f"[影巢签到] 请求签到: url={base_url}/, is_gambler={is_gambler}")
            
            resp = requests.post(
                url=f"{base_url}/",
                headers=headers,
                cookies=cookies,
                data=data,
                proxies=self._proxies(),
                timeout=30,
                verify=False
            )
            
            # 确保响应以 UTF-8 解码（影巢返回的是 UTF-8 编码）
            response_text = resp.content.decode('utf-8', errors='replace')
            
            logger.info(f"[影巢签到] 响应状态: {resp.status_code}, 内容: {response_text[:500] if response_text else 'empty'}")
            
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}", 0
            
            # 解析响应
            signin_result = self._parse_signin_response(response_text)
            
            logger.info(f"[影巢签到] 解析结果: success={signin_result.get('success')}, already_signed={signin_result.get('already_signed')}, message={signin_result.get('message')}, points={signin_result.get('points')}")
            
            message = signin_result.get('message', '签到失败')
            description = signin_result.get('description', '')
            full_message = message + ('，' + description if description else '')
            points_earned = signin_result.get('points', 0)
            
            # 检查是否成功
            if signin_result.get('success'):
                # 构建包含积分的结果
                if points_earned != 0:
                    return True, f"签到成功，获得 {points_earned} 积分", points_earned
                return True, full_message, points_earned
            
            # 检查是否已签到（这也算成功，不重试）
            if signin_result.get('already_signed'):
                return True, "今日已签到，明天再来", 0
            
            # 额外检查：响应中包含乱码的"签到"或"已经"
            if 'ç­¾å°' in full_message or 'å·²ç»' in full_message:
                return True, "今日已签到，明天再来", 0
            
            return False, full_message, 0
            
        except Exception as e:
            logger.error(f"[影巢签到] 签到请求异常: {e}")
            return False, str(e), 0
    
    def checkin(self, is_gambler: bool = False, retry_count: int = 0) -> dict:
        """执行签到"""
        config = self._get_config()
        cookie = config.get("cookie", "")
        base_url = (config.get("base_url") or HDHIVE_BASE).rstrip("/")
        max_retries = int(config.get("max_retries", 3))
        retry_interval = int(config.get("retry_interval", 30))
        
        if not cookie:
            new_cookie = self._auto_login()
            if new_cookie:
                cookie = new_cookie
                from app.plugins import save_plugin_config
                save_plugin_config(self.id, {**config, "cookie": cookie})
            else:
                return {"status": "error", "message": "未配置 Cookie 且自动登录失败"}
        
        cookies = {}
        for item in cookie.split(';'):
            if '=' in item:
                name, value = item.strip().split('=', 1)
                cookies[name] = value
        
        token = cookies.get('token')
        if not token:
            return {"status": "error", "message": "Cookie 中缺少 token"}
        
        # 执行签到
        success, message, points_earned = self._signin_base(cookies, token, base_url, is_gambler)
        
        if success:
            # 获取用户信息
            user_info = self._fetch_user_info(cookies, token, base_url)
            
            # 判断是否已签到
            already_checked = '已经签到' in message or '签到过' in message
            status = "已签到" if already_checked else "签到成功"
            
            # 积分已在 _signin_base 中解析
            
            # 保存签到记录
            sign_data = {
                "date": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "status": status,
                "message": message,
                "points": points_earned,
                "days": 0,
                "is_gambler": is_gambler,
                "user_info": user_info
            }
            self._save_sign_history(sign_data)
            self._send_notification(sign_data)
            
            return {"status": "success", "data": sign_data, "message": message}
        
        # 签到失败，检查是否需要刷新 Cookie
        if any(k in message for k in ['未授权', 'Unauthorized', 'token', '过期', 'expired', '登录']):
            new_cookie = self._auto_login()
            if new_cookie:
                from app.plugins import save_plugin_config
                save_plugin_config(self.id, {**config, "cookie": new_cookie})
                if retry_count == 0:
                    return self.checkin(is_gambler, retry_count + 1)
        
        # 重试
        if retry_count < max_retries:
            logger.info(f"[影巢签到] 签到失败，{retry_interval}秒后重试")
            time.sleep(retry_interval)
            return self.checkin(is_gambler, retry_count + 1)
        
        # 最终失败
        sign_data = {
            "date": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "status": "签到失败",
            "message": message,
            "is_gambler": is_gambler
        }
        self._save_sign_history(sign_data)
        
        return {"status": "error", "message": message}
    
    def _parse_signin_response(self, response_text: str) -> dict:
        """解析签到响应（参考 MoviePilot 实现）
        
        响应格式：
        0:{"a":"$@1","f":"","b":"","q":"","i":false}
        1:{"response":{"success":true,"message":"签到成功","code":"200"}}
        或
        1:{"error":{"success":false,"message":"签到失败","description":"你已经签到过了"}}
        
        影巢返回的 message 格式示例：
        - "签到成功，获得 5 积分"
        - "签到成功，获得 -3 积分"（赌狗模式扣分）
        - "你已经签到过了"
        """
        try:
            if not response_text:
                return {"success": False, "message": "响应为空"}
            
            lines = response_text.strip().split('\n')
            for line in lines:
                if not line.strip():
                    continue
                # 查找以数字开头后跟冒号的行
                if ':' in line and line.strip()[0].isdigit():
                    # 提取冒号后的 JSON 部分
                    json_part = line.split(':', 1)[1].strip()
                    if json_part.startswith('{') and json_part.endswith('}'):
                        try:
                            parsed = json.loads(json_part)
                            # 处理新的响应格式
                            if 'response' in parsed:
                                result = parsed['response']
                                # 尝试从 message 中提取积分
                                message = result.get('message', '')
                                result['points'] = self._extract_points(message)
                                return result
                            elif 'error' in parsed:
                                # error 格式: {"success":false,"message":"...","description":"..."}
                                error_data = parsed['error']
                                # 检查是否已签到（这也算成功）
                                desc = error_data.get('description', '')
                                msg = error_data.get('message', '')
                                if '已经签到' in desc or '签到过' in desc or '已经签到' in msg:
                                    error_data['already_signed'] = True
                                error_data['points'] = self._extract_points(msg + ' ' + desc)
                                return error_data
                            elif 'success' in parsed:
                                message = parsed.get('message', '')
                                parsed['points'] = self._extract_points(message)
                                return parsed
                        except json.JSONDecodeError:
                            continue
            
            return {"success": False, "message": "响应格式错误"}
        except Exception as e:
            logger.error(f"[影巢签到] 解析响应失败: {e}")
            return {"success": False, "message": str(e)}
    
    def _extract_points(self, message: str) -> int:
        """从消息中提取积分变化
        
        支持格式：
        - "签到成功，获得 5 积分"
        - "签到成功，获得 -3 积分"
        - "获得 10 积分"
        - "获得-5积分"
        """
        if not message:
            return 0
        
        # 尝试多种正则模式匹配积分
        patterns = [
            r'获得\s*(-?\d+)\s*积分',  # 获得 5 积分 / 获得 -3 积分
            r'获得\s*(-?\d+)积分',      # 获得5积分
            r'([-+])\s*(\d+)\s*积分',   # +5 积分 / -3 积分
            r'积分\s*([+-]?\d+)',       # 积分+5 / 积分-3
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                groups = match.groups()
                if len(groups) == 1:
                    return int(groups[0])
                elif len(groups) == 2:
                    sign = 1 if groups[0] == '+' else -1
                    return sign * int(groups[1])
        
        return 0
    
    def _get_next_action_cached(self, cookies: dict, token: str, base_url: str) -> str:
        """获取 next-action（带缓存，但失败时清除缓存重试）"""
        # 每次签到前都重新获取，因为 action 可能频繁变化
        # 缓存时间缩短到 1 小时
        if self._next_action_cache and time.time() - self._next_action_cache_time < 60 * 60:
            return self._next_action_cache
        
        next_action = self._get_next_action(cookies, token, base_url)
        self._next_action_cache = next_action
        self._next_action_cache_time = time.time()
        return next_action
    
    def _get_next_action(self, cookies: dict, token: str, base_url: str) -> str:
        """动态获取 next-action 值（参考 MoviePilot 实现）"""
        default_action = "40731c4a2b41c8873577eae3cbd31ab9d2aeb1d8c5"
        
        try:
            cookie_str = self._get_config().get("cookie", "")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Cookie': cookie_str,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            logger.info(f"[影巢签到] 正在动态获取 next-action...")
            
            # 1. 获取主页 HTML（签到在主页触发）
            resp = requests.get(base_url, headers=headers, cookies=cookies,
                              proxies=self._proxies(), timeout=30, verify=False)
            
            if resp.status_code != 200:
                logger.warning(f"[影巢签到] 获取主页失败: {resp.status_code}，使用默认 action")
                return default_action
            
            # 2. 查找所有 JS chunk 文件（使用 MoviePilot 的格式）
            # 格式: self.__next_f.push..."xxx.js"
            script_pattern = r'self\.__next_f\.push[^\"]*"([^"]*\.js)"'
            scripts = re.findall(script_pattern, resp.text)
            
            logger.info(f"[影巢签到] 找到 {len(scripts)} 个 JS chunks")
            
            # 如果没找到，尝试其他模式
            if not scripts:
                # 尝试模式2: <script src="/_next/static/chunks/xxx.js">
                script_pattern2 = r'<script[^>]*src="(/_next/static/chunks/[^"]+\.js)"'
                scripts = re.findall(script_pattern2, resp.text)
                logger.info(f"[影巢签到] 模式2 找到 {len(scripts)} 个 JS chunks")
            
            if not scripts:
                # 尝试模式3: "chunks/xxx.js"
                script_pattern3 = r'"(/_next/static/chunks/[^"]+\.js)"'
                scripts = re.findall(script_pattern3, resp.text)
                logger.info(f"[影巢签到] 模式3 找到 {len(scripts)} 个 JS chunks")
            
            # 输出部分页面内容用于调试
            if not scripts:
                logger.warning(f"[影巢签到] 未找到 JS chunks，页面内容前500字符: {resp.text[:500]}")
                return default_action
            
            logger.info(f"[影巢签到] 共找到 {len(scripts)} 个 JS 文件，第一个: {scripts[0] if scripts else 'N/A'}")
            
            # 3. 逐个检查 JS 文件，查找 checkIn 相关的 action
            from urllib.parse import urljoin
            first_found_action = None
            for script_src in scripts:
                js_url = urljoin(base_url, script_src)
                
                try:
                    js_resp = requests.get(js_url, headers=headers, cookies=cookies,
                                          proxies=self._proxies(), timeout=30, verify=False)
                    
                    if js_resp.status_code == 200:
                        # 查找包含 checkIn 的 createServerReference 调用
                        # 多种格式匹配
                        patterns = [
                            r'createServerReference\)\("([a-fA-F0-9]{20,50})"[^)]*?"checkIn"\)',
                            r'createServerReference\)\("([a-fA-F0-9]{20,50})"[^)]*?checkIn',
                            r'"([a-fA-F0-9]{20,50})"[^}]{0,200}checkIn',
                            r'"([a-fA-F0-9]{20,50})"[^}]{0,200}CheckIn',
                            r'checkIn[^}]{0,200}"([a-fA-F0-9]{20,50})"',
                        ]
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, js_resp.text, re.IGNORECASE)
                            if matches:
                                next_action = matches[0]
                                logger.info(f"[影巢签到] ✅ 动态获取 next-action 成功: {next_action}")
                                return next_action
                        
                        # 调试：输出 JS 文件中的 createServerReference 调用
                        all_actions = re.findall(r'createServerReference\)\("([a-fA-F0-9]{20,50})"', js_resp.text)
                        if all_actions:
                            logger.info(f"[影巢签到] JS {script_src[-30:]} 中的 actions: {all_actions[:3]}")
                            # 记录找到的第一个 action
                            if not first_found_action:
                                first_found_action = all_actions[0]
                            # 如果找到 action 但没有匹配到 checkIn，返回第一个作为尝试
                            # 因为在用户页面的 JS 可能就是签到相关的
                            if 'user' in script_src or 'checkin' in script_src.lower():
                                logger.info(f"[影巢签到] ✅ 从用户相关 JS 中获取 action: {all_actions[0]}")
                                return all_actions[0]
                            
                except Exception as e:
                    logger.debug(f"[影巢签到] 获取 JS 失败 {js_url}: {e}")
                    continue
            
            # 尝试从页面 HTML 中直接查找 action
            # 格式可能直接嵌入在页面中
            page_actions = re.findall(r'"([a-fA-F0-9]{20,50})"', resp.text)
            if page_actions:
                logger.info(f"[影巢签到] 页面中找到的 action 候选: {page_actions[:5]}")
            
            # 如果找到了 checkIn 相关的 action，使用它
            # 否则使用默认值（你抓包获取的正确值）
            logger.info(f"[影巢签到] ✅ 使用默认 action: {default_action}")
            return default_action
            
        except Exception as e:
            logger.error(f"[影巢签到] 获取 next-action 异常: {e}")
            return default_action
    
    def _get_login_action(self, session, base_url: str) -> Optional[str]:
        """动态获取登录的 next-action 值"""
        default_action = "602b5a3af7ab2e93be6a14001ca83c1be491ccecea"
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            logger.info("[影巢签到] 正在动态获取登录 action...")
            
            # 1. 获取登录页面 HTML
            login_url = f"{base_url}/login"
            resp = session.get(login_url, headers=headers, timeout=30, verify=False)
            
            if resp.status_code != 200:
                logger.warning(f"[影巢签到] 获取登录页面失败: {resp.status_code}")
                return None
            
            # 2. 查找所有 JS chunk 文件
            script_patterns = [
                r'self\.__next_f\.push[^"]*"([^"]*\.js)"',
                r'<script[^>]*src="(/_next/static/chunks/[^"]+\.js)"',
                r'"(/_next/static/chunks/[^"]+\.js)"',
            ]
            
            scripts = []
            for pattern in script_patterns:
                scripts = re.findall(pattern, resp.text)
                if scripts:
                    break
            
            logger.info(f"[影巢签到] 登录页找到 {len(scripts)} 个 JS chunks")
            
            if not scripts:
                return None
            
            # 3. 逐个检查 JS 文件，查找 login 相关的 action
            from urllib.parse import urljoin
            for script_src in scripts:
                js_url = urljoin(base_url, script_src)
                
                try:
                    js_resp = session.get(js_url, headers=headers, timeout=30, verify=False)
                    
                    if js_resp.status_code == 200:
                        # 查找包含 login/signin 的 createServerReference 调用
                        # 多种模式匹配
                        patterns = [
                            r'createServerReference\)\("([a-fA-F0-9]{42})"[^)]*?"login"\)',
                            r'createServerReference\)\("([a-fA-F0-9]{42})"[^)]*?"signin"\)',
                            r'createServerReference\)\("([a-fA-F0-9]{42})"[^)]*?"SignIn"\)',
                            r'createServerReference\)\("([a-fA-F0-9]{42})"[^)]*?"LogIn"\)',
                            # 尝试匹配任何 createServerReference 调用（登录页通常只有登录相关的）
                            r'createServerReference\)\("([a-fA-F0-9]{42})"',
                        ]
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, js_resp.text)
                            if matches:
                                login_action = matches[0]
                                # 如果是最后一个模式（通用匹配），需要验证是否在登录页相关代码中
                                if pattern == patterns[-1]:
                                    # 检查这个 action 附近是否有 login 相关关键字
                                    context_pattern = f'{login_action}[^}}]{{0,200}}'
                                    context_match = re.search(context_pattern, js_resp.text)
                                    if context_match and ('login' in context_match.group(0).lower() or 'signin' in context_match.group(0).lower() or 'user' in context_match.group(0).lower()):
                                        logger.info(f"[影巢签到] ✅ 动态获取登录 action 成功: {login_action}")
                                        return login_action
                                else:
                                    logger.info(f"[影巢签到] ✅ 动态获取登录 action 成功: {login_action}")
                                    return login_action
                                
                except Exception as e:
                    logger.debug(f"[影巢签到] 获取 JS 失败 {js_url}: {e}")
                    continue
            
            logger.warning("[影巢签到] 未找到 login action")
            return None
            
        except Exception as e:
            logger.error(f"[影巢签到] 获取登录 action 异常: {e}")
            return None
    
    def _auto_login(self) -> Optional[str]:
        """自动登录获取 Cookie（使用 Next.js Server Action 方式）"""
        config = self._get_config()
        username = config.get("username", "").strip()
        password = config.get("password", "").strip()
        base_url = (config.get("base_url") or HDHIVE_BASE).rstrip("/")
        
        if not username or not password:
            logger.warning("[影巢签到] 未配置用户名或密码")
            return None
        
        try:
            logger.info(f"[影巢签到] 尝试自动登录: {username}, 站点: {base_url}")
            session = requests.Session()
            proxies = self._proxies()
            if proxies:
                session.proxies.update(proxies)
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh,zh-CN;q=0.9,en;q=0.8',
            }
            
            # 1. 访问登录页面获取 cookies 和 next-action
            login_url = f"{base_url}/login"
            logger.info(f"[影巢签到] 访问登录页面: {login_url}")
            resp = session.get(login_url, headers=headers, timeout=30, verify=False)
            logger.info(f"[影巢签到] 登录页面响应: {resp.status_code}")
            
            if resp.status_code != 200:
                logger.error(f"[影巢签到] 访问登录页面失败: {resp.status_code}")
                return None
            
            # 获取 csrf_access_token cookie
            csrf_token = None
            for cookie in session.cookies:
                if cookie.name == 'csrf_access_token':
                    csrf_token = cookie.value
                    logger.info(f"[影巢签到] 获取到 csrf_access_token")
                    break
            
            # 2. 动态获取登录 action
            login_action = self._get_login_action(session, base_url)
            if not login_action:
                login_action = "602b5a3af7ab2e93be6a14001ca83c1be491ccecea"  # 备用默认值
            logger.info(f"[影巢签到] 使用登录 action: {login_action}")
            
            # 3. 使用 Server Action 登录
            action_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/x-component',
                'Accept-Language': 'zh,zh-CN;q=0.9,en;q=0.8',
                'Content-Type': 'text/plain;charset=UTF-8',
                'Origin': base_url,
                'Referer': login_url,
                'Next-Action': login_action,
            }
            
            # 构建请求数据（格式: [{"username": "xxx", "password": "xxx"}]）
            login_body = json.dumps([{"username": username, "password": password}])
            
            logger.info(f"[影巢签到] 发送登录请求到: {login_url}")
            logger.info(f"[影巢签到] 请求体: {login_body}")
            action_resp = session.post(login_url, headers=action_headers,
                                       data=login_body, timeout=30, verify=False,
                                       allow_redirects=False)  # 禁止自动重定向，捕获原始响应
            
            logger.info(f"[影巢签到] 登录响应: status={action_resp.status_code}")
            logger.info(f"[影巢签到] 响应内容: {action_resp.text[:500] if action_resp.text else 'empty'}")
            logger.info(f"[影巢签到] 响应头: {dict(action_resp.headers)}")
            logger.info(f"[影巢签到] Session cookies: {[c.name + '=' + c.value[:20] + '...' for c in session.cookies]}")
            
            # 4. 解析响应获取 token
            # 响应可能是 303 redirect 或 200
            logger.info(f"[影巢签到] 响应头 Set-Cookie: {action_resp.headers.get('Set-Cookie', 'N/A')[:100]}")
            
            # 从 Set-Cookie 头获取 token（最重要）
            token = None
            set_cookie = action_resp.headers.get('Set-Cookie', '')
            token_match = re.search(r'token=([^;]+)', set_cookie)
            if token_match:
                token = token_match.group(1)
                logger.info(f"[影巢签到] 从 Set-Cookie 获取到 token")
            
            # 从 cookies 中获取 token
            if not token:
                for cookie in session.cookies:
                    if cookie.name == 'token':
                        token = cookie.value
                        logger.info(f"[影巢签到] 从 session.cookies 获取到 token")
                        break
            
            if token:
                cookie_parts = [f"token={token}"]
                for cookie in session.cookies:
                    if cookie.name not in ['token'] and cookie.value:
                        cookie_parts.append(f"{cookie.name}={cookie.value}")
                cookie_str = "; ".join(cookie_parts)
                logger.info(f"[影巢签到] ✅ 登录成功，Cookie 长度: {len(cookie_str)}")
                return cookie_str
            else:
                logger.warning(f"[影巢签到] 登录响应中未找到 token, status={action_resp.status_code}")
            
            # 如果 Server Action 失败，尝试传统方式
            return self._legacy_login(session, username, password, base_url)
            
        except Exception as e:
            logger.error(f"[影巢签到] 自动登录异常: {e}")
            return None
    
    def _legacy_login(self, session, username: str, password: str, base_url: str) -> Optional[str]:
        """传统 API 登录方式（备用）"""
        login_url = f"{base_url}/login"
        
        # 尝试多种登录 API
        login_apis = [
            f"{base_url}/api/customer/user/login",
            f"{base_url}/api/customer/auth/login",
            f"{base_url}/api/auth/login",
            f"{base_url}/api/user/login",
        ]
        
        for login_api in login_apis:
            try:
                logger.info(f"[影巢签到] 尝试传统 API: {login_api}")
                login_headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json, text/plain, */*',
                    'Content-Type': 'application/json',
                    'Origin': base_url,
                    'Referer': login_url,
                }
                
                login_resp = session.post(login_api, headers=login_headers,
                                         json={"username": username, "password": password},
                                         timeout=30, verify=False)
                
                if login_resp.status_code == 200:
                    data = login_resp.json()
                    if data.get('success') or data.get('token'):
                        token = data.get('token') or data.get('data', {}).get('token')
                        if not token:
                            for cookie in session.cookies:
                                if cookie.name == 'token':
                                    token = cookie.value
                        
                        if token:
                            cookie_parts = [f"token={token}"]
                            for cookie in session.cookies:
                                if cookie.name not in ['token'] and cookie.value:
                                    cookie_parts.append(f"{cookie.name}={cookie.value}")
                            cookie_str = "; ".join(cookie_parts)
                            logger.info(f"[影巢签到] ✅ 传统 API 登录成功")
                            return cookie_str
            except Exception as e:
                logger.debug(f"[影巢签到] 传统 API 失败 {login_api}: {e}")
        
        logger.error("[影巢签到] 所有登录方式都失败")
        return None
    
    def _fetch_user_info(self, cookies: dict, token: str, base_url: str) -> dict:
        """获取用户信息"""
        try:
            user_id = None
            try:
                decoded = decode_jwt_payload(token)
                user_id = decoded.get('user_id')
            except:
                pass
            
            if not user_id:
                return {}
            
            referer = f"{base_url}/user/{user_id}"
            cookie_str = self._get_config().get("cookie", "")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh,zh-CN;q=0.9,en;q=0.8',
                'Cookie': cookie_str,
                'Referer': referer,
            }
            
            # 尝试从用户页面获取信息
            resp = requests.get(referer, headers=headers, cookies=cookies,
                              proxies=self._proxies(), timeout=30, verify=False)
            
            if resp.status_code == 200:
                # 尝试从页面中提取用户信息
                text = resp.text
                
                # 提取昵称
                nickname = None
                nickname_match = re.search(r'"nickname"\s*:\s*"([^"]+)"', text)
                if nickname_match:
                    nickname = nickname_match.group(1)
                
                # 提取积分
                points = None
                points_match = re.search(r'"points"\s*:\s*(-?\d+)', text)
                if points_match:
                    points = int(points_match.group(1))
                
                # 提取签到天数
                signin_days = None
                days_match = re.search(r'"signin_days_total"\s*:\s*(\d+)', text)
                if days_match:
                    signin_days = int(days_match.group(1))
                
                if nickname or points is not None:
                    return {
                        'id': user_id,
                        'nickname': nickname,
                        'points': points,
                        'signin_days_total': signin_days,
                    }
            
            # 备用：尝试 API 接口
            api_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Origin': base_url,
                'Referer': referer,
                'Authorization': f'Bearer {token}',
            }
            
            resp = requests.get(f"{base_url}/api/customer/user/info", headers=api_headers,
                              cookies=cookies, proxies=self._proxies(), timeout=30, verify=False)
            
            if resp.status_code == 200:
                data = resp.json()
                detail = (data.get('response') or {}).get('data') or data.get('detail') or data.get('data') or {}
                if isinstance(detail, dict):
                    user_meta = detail.get('user_meta', {}) or {}
                    return {
                        'id': detail.get('id') or detail.get('member_id'),
                        'nickname': detail.get('nickname') or detail.get('member_name'),
                        'points': user_meta.get('points'),
                        'signin_days_total': user_meta.get('signin_days_total'),
                    }
        except Exception as e:
            logger.warning(f"[影巢签到] 获取用户信息失败: {e}")
        return {}
    
    def _save_sign_history(self, sign_data: dict):
        """保存签到历史"""
        try:
            config = self._get_config()
            history = config.get("_sign_history", [])
            history.append(sign_data)
            history_days = int(config.get("history_days", 30))
            now = datetime.datetime.now()
            valid_history = []
            for record in history:
                try:
                    record_date = datetime.datetime.strptime(record.get("date", ""), '%Y-%m-%d %H:%M:%S')
                    if (now - record_date).days < history_days:
                        valid_history.append(record)
                except:
                    valid_history.append(record)
            from app.plugins import save_plugin_config
            save_plugin_config(self.id, {**config, "_sign_history": valid_history[-100:]})
        except Exception as e:
            logger.error(f"[影巢签到] 保存历史失败: {e}")
    
    def _send_notification(self, sign_data: dict):
        """发送签到通知"""
        config = self._get_config()
        if not config.get("notify_bot"):
            return
        
        status = sign_data.get("status", "未知")
        message = sign_data.get("message", "—")
        points = sign_data.get("points")
        is_gambler = sign_data.get("is_gambler", False)
        user_info = sign_data.get("user_info", {})
        sign_time = sign_data.get("date", "")
        
        mode = "赌狗模式 🎲" if is_gambler else "普通模式"
        title = "【✅ 影巢签到成功】" if "成功" in status else "【ℹ️ 影巢重复签到】" if "已签到" in status else "【❌ 影巢签到失败】"
        
        msg_lines = [title, f"🕐 时间：{sign_time}", f"🎯 模式：{mode}", f"✨ 状态：{status}"]
        # 积分显示（points 是整数或 None）
        if points is not None and isinstance(points, (int, float)):
            msg_lines.append(f"🎁 奖励：{'+' if points >= 0 else ''}{int(points)} 积分")
        if user_info.get("nickname"):
            msg_lines.append(f"👤 用户：{user_info.get('nickname')}")
        if user_info.get("points") is not None:
            msg_lines.append(f"💰 当前积分：{user_info.get('points')}")
        msg_lines.append(f"💬 {message}")
        
        try:
            from app.services.bot_service import bot
            bot.send_message("sys_notify", "\n".join(msg_lines), platform="all")
        except Exception as e:
            logger.error(f"[影巢签到] 发送通知失败: {e}")
    
    def get_checkin_status(self) -> dict:
        """获取签到状态"""
        config = self._get_config()
        history = config.get("_sign_history", [])
        last_checkin = history[-1] if history else None
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        today_checked = last_checkin and last_checkin.get("date", "").startswith(today)
        
        return {
            "status": "success",
            "data": {
                "enabled": self._enabled,
                "today_checked": today_checked,
                "last_checkin": last_checkin,
                "consecutive_days": config.get("_consecutive_days", 0),
                "total_checkins": len([h for h in history if "成功" in h.get("status", "")])
            }
        }
    
    def get_checkin_history(self, limit: int = 30) -> dict:
        """获取签到历史"""
        config = self._get_config()
        history = config.get("_sign_history", [])
        return {"status": "success", "data": {"history": history[-limit:][::-1], "total": len(history)}}
    
    def get_user_info(self) -> dict:
        """获取用户信息"""
        config = self._get_config()
        cookie = config.get("cookie", "")
        base_url = (config.get("base_url") or HDHIVE_BASE).rstrip("/")
        if not cookie:
            return {"status": "error", "message": "未配置 Cookie"}
        cookies = {}
        for item in cookie.split(';'):
            if '=' in item:
                name, value = item.strip().split('=', 1)
                cookies[name] = value
        token = cookies.get('token')
        if not token:
            return {"status": "error", "message": "Cookie 中缺少 token"}
        user_info = self._fetch_user_info(cookies, token, base_url)
        return {"status": "success", "data": user_info}
    
    def _checkin_loop(self):
        """自动签到线程"""
        time.sleep(30)
        while self._running and self._enabled:
            try:
                config = self._get_config()
                mode = config.get("checkin_mode", "")
                if "normal" in mode or "gambler" in mode:
                    now = datetime.datetime.now()
                    current_date = now.strftime("%Y-%m-%d")
                    checkin_time = config.get("checkin_time", "08:00").strip()
                    time_match = re.match(r'^(\d{1,2}):?(\d{2})?', checkin_time)
                    checkin_hour = 8
                    checkin_minute = 0
                    if time_match:
                        checkin_hour = max(0, min(23, int(time_match.group(1))))
                        if time_match.group(2):
                            checkin_minute = max(0, min(59, int(time_match.group(2))))
                    
                    if (now.hour == checkin_hour and now.minute == checkin_minute and
                        self._last_checkin_date != current_date):
                        is_gambler = "gambler" in mode
                        logger.info(f"[影巢签到] 开始自动签到: 赌狗模式={is_gambler}")
                        self.checkin(is_gambler=is_gambler)
                        self._last_checkin_date = current_date
            except Exception as e:
                logger.error(f"[影巢签到] 自动签到检查异常: {e}")
            for _ in range(60):
                if not self._running:
                    return
                time.sleep(1)


# 创建插件实例
plugin = HDHiveSignPlugin()
