"""
115 网盘转存插件
管理员通过主机器人发送含 115 链接、磁力链接、ed2k链接的消息，自动转存到指定文件夹或添加离线下载
"""
import re
import json
import time
import logging
import threading
from app.plugins.base import PluginBase
from app.core.event_bus import bus
from app.infra.clients.cloud115_client import cloud115_client

logger = logging.getLogger("uvicorn")

# 115 链接正则：匹配 115://开头 或 115.com/s/ 分享链接
LINK_PATTERN = re.compile(r'(115://[^\s<>"]+|https?://(?:www\.)?115(?:cdn)?\.com/s/[^\s<>"]+)')
# 磁力链接正则
MAGNET_PATTERN = re.compile(r'(magnet:\?[^\s<>""]+)')
# ed2k 链接正则 - 改为只排除 <> 和双引号，允许其他所有字符（包括单引号、空格等）
ED2K_PATTERN = re.compile(r'(ed2k://[^<>"]+)', re.IGNORECASE)


class Cloud115Plugin(PluginBase):
    id = "cloud115"
    name = "115 网盘转存"
    description = "管理员发送 115 链接到主机器人，自动转存到网盘指定文件夹"
    icon = "fa-cloud-arrow-down"
    icon_color = "from-blue-500 to-cyan-500"
    version = "1.0.0"
    author = "EmbyPulse"

    def __init__(self):
        super().__init__()
        self._subscribed = False
        self._setup_routes()

    def _setup_routes(self):
        """注册插件 API 路由"""
        from fastapi import Request
        from app.domains.users.auth import is_admin_user

        @self.router.get("/folders")
        def get_folders(request: Request):
            """获取配置的文件夹列表"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            config = self._get_config()
            folders = self._parse_folders(config)
            # 返回简化的文件夹列表
            return {"status": "success", "folders": [{"id": f["cid"], "name": f["name"]} for f in folders]}

        @self.router.post("/transfer")
        async def do_transfer(request: Request):
            """手动转存链接"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            try:
                data = await request.json()
                link = data.get("link", "").strip()
                folder_id = data.get("folder_id")  # 可选
            except:
                return {"status": "error", "message": "参数错误"}

            if not link:
                return {"status": "error", "message": "缺少链接"}

            config = self._get_config()
            cookie = config.get("cookie", "")
            if not cookie:
                return {"status": "error", "message": "未配置 115 Cookie"}

            # 确定 folder_id
            if folder_id:
                # 从配置中查找文件夹名称
                folders = self._parse_folders(config)
                folder_name = next((f["name"] for f in folders if f["cid"] == folder_id), "指定文件夹")
            else:
                folders = self._parse_folders(config)
                if folders:
                    folder_id = folders[0].get("cid", "0")
                    folder_name = folders[0].get("name", "默认")
                else:
                    folder_id = "0"
                    folder_name = "根目录"

            result = self._do_transfer_sync(link, folder_id, folder_name, cookie)
            return result
        
        @self.router.post("/transfer_link")
        async def transfer_link_api(request: Request):
            """给影巢插件调用的转存接口"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            try:
                data = await request.json()
                link = data.get("link", "").strip()
                folder_id = data.get("folder_id")  # 可选
            except:
                return {"status": "error", "message": "参数错误"}

            if not link:
                return {"status": "error", "message": "缺少链接"}

            config = self._get_config()
            cookie = config.get("cookie", "")
            if not cookie:
                return {"status": "error", "message": "未配置 115 Cookie"}

            # 确定 folder_id
            if not folder_id:
                folders = self._parse_folders(config)
                if folders:
                    folder_id = folders[0].get("cid", "0")
                else:
                    folder_id = "0"

            result = self._do_transfer_sync(link, folder_id, "转存", cookie)
            return result

    def on_enable(self):
        if not self._subscribed:
            bus.subscribe("bot.admin_message", self._on_admin_message)
            self._subscribed = True
        logger.info("🔌 [115转存] 插件已启用")

    def on_disable(self):
        if self._subscribed:
            bus.unsubscribe("bot.admin_message", self._on_admin_message)
            self._subscribed = False
        logger.info("🔌 [115转存] 插件已禁用")

    def get_config_schema(self):
        return [
            {"key": "cookie", "label": "115 Cookie", "type": "password", "placeholder": "从浏览器获取 115 的 Cookie", "hint": "登录 115.com 后从浏览器开发者工具复制 Cookie"},
            {"key": "folders", "label": "转存目标文件夹", "type": "text", "placeholder": "电影:3048255074643880964,剧集:2048255074643880123", "hint": "格式：名称:文件夹ID，多个用英文逗号分隔。单个文件夹直接转存，多个会让你选择"},
            {"key": "offline_folders", "label": "离线下载保存文件夹", "type": "text", "placeholder": "离线电影:3048255074643880964,离线剧集:2048255074643880123", "hint": "格式：名称:文件夹ID，多个用英文逗号分隔。磁力/ed2k离线下载保存的文件夹，单个直接保存，多个会让你选择"},
            {"key": "auto_offline", "label": "自动识别离线下载", "type": "toggle", "hint": "自动识别磁力链接和ed2k链接并添加离线下载"},
            {"key": "notify_enabled", "label": "启用通知", "type": "toggle", "hint": "开启后，插件运行状态会发送到全局通知"},
        ]

    def _get_config(self):
        from app.plugins import get_plugin_config
        return get_plugin_config(self.id)

    def _parse_folders(self, config):
        """解析文件夹配置：名称:CID,名称:CID 格式（从 config 对象读取）"""
        return self._parse_folders_string(config.get("folders", ""))

    def _parse_folders_string(self, raw):
        """解析文件夹配置字符串：名称:CID,名称:CID 格式"""
        if not raw:
            return []
        # 兼容旧JSON格式
        if raw.strip().startswith("["):
            try:
                return json.loads(raw)
            except:
                pass
        folders = []
        for part in raw.split(","):
            part = part.strip()
            if ":" in part:
                name, cid = part.split(":", 1)
                folders.append({"name": name.strip(), "cid": cid.strip()})
            elif part.isdigit():
                folders.append({"name": f"文件夹{len(folders)+1}", "cid": part})
        return folders

    def _log(self, msg, level="info"):
        """记录日志（兼容旧代码）"""
        self.log(msg, level=level)

    def _on_admin_message(self, text, chat_id, platform):
        """监听管理员机器人消息，检测 115 链接、磁力链接、ed2k链接"""
        logger.info(f"[115转存] 收到消息: enabled={self._enabled}, text={text[:80]}...")
        if not self._enabled:
            return

        config = self._get_config()
        cookie = config.get("cookie", "")
        auto_offline = config.get("auto_offline", False)

        # 检测115链接
        links_115 = LINK_PATTERN.findall(text)
        # 检测磁力链接
        magnets = MAGNET_PATTERN.findall(text) if auto_offline else []
        # 检测ed2k链接
        ed2ks = ED2K_PATTERN.findall(text) if auto_offline else []

        logger.info(f"[115转存] 匹配到 115链接:{len(links_115)} 个, 磁力:{len(magnets)} 个, ed2k:{len(ed2ks)} 个")

        # 处理115链接转存
        if links_115:
            threading.Thread(target=self._process_links, args=(links_115, chat_id, platform), daemon=True).start()

        # 处理离线下载（磁力+ed2k）
        if (magnets or ed2ks) and cookie:
            offline_folders = self._parse_folders_string(config.get("offline_folders", ""))

            if not offline_folders:
                # 没有配置离线文件夹，保存到根目录
                threading.Thread(target=self._process_offline, args=(magnets, ed2ks, None, cookie, chat_id, platform), daemon=True).start()
            elif len(offline_folders) == 1:
                # 单个文件夹直接使用
                folder = offline_folders[0]
                threading.Thread(target=self._process_offline, args=(magnets, ed2ks, folder, cookie, chat_id, platform), daemon=True).start()
            else:
                # 多个文件夹：发选择按钮让管理员选
                import hashlib
                link_key = hashlib.md5(",".join(magnets + ed2ks).encode()).hexdigest()[:8]
                _offline_cache[link_key] = {"magnets": magnets, "ed2ks": ed2ks}

                keyboard = {"inline_keyboard": []}
                for f in offline_folders:
                    keyboard["inline_keyboard"].append([{
                        "text": f"📁 {f.get('name', '未命名')}",
                        "callback_data": f"p115_ol_{link_key}_{f.get('cid', '0')}"
                    }])

                # 添加"根目录"选项
                keyboard["inline_keyboard"].append([{
                    "text": "📂 根目录",
                    "callback_data": f"p115_ol_{link_key}_0"
                }])

                msg = f"🔽 <b>[115离线]</b> 检测到 {len(magnets) + len(ed2ks)} 个离线链接\n\n请选择保存目标文件夹："
                self._notify(chat_id, msg, platform, reply_markup=keyboard)
        elif (magnets or ed2ks) and not cookie:
            if not links_115:  # 只有离线链接没有115链接时
                self._notify(chat_id, "❌ [115离线] 未配置 Cookie，无法添加离线下载", platform)

    def _process_offline(self, magnets, ed2ks, folder_info, cookie, chat_id, platform):
        """处理离线下载（磁力链接和ed2k链接）

        Args:
            magnets: 磁力链接列表
            ed2ks: ed2k链接列表
            folder_info: 文件夹信息 dict 或 None（None表示根目录）
            cookie: 115 Cookie
            chat_id: 聊天ID
            platform: 平台
        """
        if not cookie:
            return

        # 提取 folder_cid 和 folder_name
        if folder_info:
            folder_cid = folder_info.get("cid", "0") if isinstance(folder_info, dict) else str(folder_info)
            folder_name = folder_info.get("name", "未命名") if isinstance(folder_info, dict) else "未命名"
        else:
            folder_cid = "0"
            folder_name = "根目录"

        total_count = len(magnets) + len(ed2ks)

        self._log(f"开始处理离线下载，磁力:{len(magnets)}个, ed2k:{len(ed2ks)}个，目标:{folder_name}({folder_cid})")
        self._notify(chat_id, f"🔄 <b>[115离线]</b> 正在添加 {total_count} 个离线下载任务...", platform)

        # 获取uid和sign
        try:
            # 获取uid
            user_resp = cloud115_client.get_nav(cookie, timeout=15)
            user_data = user_resp.json()
            uid = user_data.get("data", {}).get("user_id", "")
            logger.info(f"[115离线] 获取uid: {uid}")

            # 获取sign和time
            token_resp = cloud115_client.get_offline_space(cookie, timeout=15)
            token_data = token_resp.json()
            sign = token_data.get("sign", "")
            time_val = token_data.get("time", "")
            logger.info(f"[115离线] 获取sign: {sign[:20] if sign else ''}..., time: {time_val}")
        except Exception as e:
            logger.error(f"[115离线] 获取签名失败: {e}")
            self._notify(chat_id, f"❌ [115离线] 获取签名失败，请检查Cookie是否有效", platform)
            return

        if not uid or not sign:
            self._notify(chat_id, f"❌ [115离线] Cookie无效，无法获取用户信息", platform)
            return

        success_count = 0
        fail_count = 0

        # 收集所有需要添加的链接
        all_urls = magnets + ed2ks

        # 使用正确的API添加离线任务
        for url in all_urls:
            try:
                data = {
                    "url": url,
                    "uid": uid,
                    "sign": sign,
                    "time": time_val,
                    "wp_path_id": folder_cid,
                    "savepath": ""
                }

                resp = cloud115_client.add_offline_task(cookie, data, timeout=15)
                result = resp.json()
                logger.info(f"[115离线] 添加URL: {url[:50]}...")
                logger.info(f"[115离线] 响应: {result}")

                if result.get("state"):
                    success_count += 1
                    self._log(f"离线添加成功: {url[:50]}...")
                else:
                    fail_count += 1
                    logger.warning(f"[115离线] 添加失败: {result.get('error_msg', '未知错误')}")

            except Exception as e:
                fail_count += 1
                logger.error(f"[115离线] 异常: {e}")
            time.sleep(1)

        # 汇总结果
        folder_info_str = f" → {folder_name}" if folder_name != "根目录" else " → 根目录"
        if fail_count == 0:
            self._notify(chat_id, f"✅ <b>[115离线] 离线任务添加完成！</b>\n\n成功添加 {success_count} 个任务{folder_info_str}\n\n请前往 115 客户端查看下载进度", platform)
        else:
            self._notify(chat_id, f"⚠️ <b>[115离线] 部分任务添加完成</b>\n\n成功: {success_count} 个\n失败: {fail_count} 个{folder_info_str}", platform)

    def _process_links(self, links, chat_id, platform):
        config = self._get_config()
        cookie = config.get("cookie", "")
        if not cookie:
            self._notify(chat_id, "❌ [115转存] 未配置 Cookie，请在插件中心配置", platform)
            return

        folders = self._parse_folders(config)

        if not folders:
            self._notify(chat_id, "❌ [115转存] 未配置目标文件夹，请在插件中心配置", platform)
            return

        self._log(f"检测到 {len(links)} 个链接，开始处理")

        # 单文件夹直接转存，多文件夹发选择按钮
        if len(folders) == 1:
            target_cid = folders[0].get("cid", "0")
            target_name = folders[0].get("name", "默认")
            for i, link in enumerate(links):
                if i > 0:
                    time.sleep(3)  # 排队延迟，避免115限频
                self._do_transfer(link, target_cid, target_name, cookie, chat_id, platform)
        else:
            # 多文件夹：发 inline keyboard 让管理员选
            # 先把链接存到临时缓存
            import hashlib
            link_key = hashlib.md5(",".join(links).encode()).hexdigest()[:8]
            _transfer_cache[link_key] = links

            keyboard = {"inline_keyboard": []}
            for f in folders:
                keyboard["inline_keyboard"].append([{
                    "text": f"📁 {f.get('name', '未命名')}",
                    "callback_data": f"p115_tf_{link_key}_{f.get('cid', '0')}"
                }])
            msg = f"📦 <b>[115转存]</b> 检测到 {len(links)} 个链接\n\n请选择转存目标文件夹："
            self._notify(chat_id, msg, platform, reply_markup=keyboard)

    def _do_transfer(self, link, cid, folder_name, cookie, chat_id, platform):
        """执行单个链接的转存"""
        try:
            share_code, receive_code = self._extract_share_code(link)
            if not share_code:
                self._notify(chat_id, f"⚠️ [115转存] 无法解析链接：{link[:50]}...", platform)
                return

            info_res = cloud115_client.get_share_snap(cookie, share_code, receive_code, timeout=15)
            if info_res.status_code != 200:
                self._notify(chat_id, f"❌ [115转存] 获取分享信息失败", platform)
                return

            info = info_res.json()
            if not info.get("state"):
                self._notify(chat_id, f"❌ [115转存] 分享已失效或需要访问码：{info.get('error', '未知错误')}", platform)
                return

            # 获取文件列表
            file_list = info.get("data", {}).get("list", [])
            if not file_list:
                self._notify(chat_id, "❌ [115转存] 分享内容为空", platform)
                return

            # 执行转存
            file_ids = [str(f.get("fid") or f.get("cid")) for f in file_list]
            share_snap_id = info.get("data", {}).get("shareinfo", {}).get("snap_id", "")

            transfer_res = cloud115_client.receive_share(cookie, {
                "share_code": share_code,
                "receive_code": receive_code,
                "snap_id": share_snap_id,
                "file_id": ",".join(file_ids),
                "cid": cid
            }, timeout=15)
            result = transfer_res.json()

            if result.get("state"):
                file_names = [f.get("n", "未知") for f in file_list[:3]]
                names_str = "\n".join([f"  📄 {n}" for n in file_names])
                if len(file_list) > 3:
                    names_str += f"\n  ... 共 {len(file_list)} 个文件"
                self._log(f"转存成功 → {folder_name}，{len(file_list)} 个文件")
                self._notify(chat_id, f"✅ <b>[115转存] 转存成功！</b>\n\n📁 目标：{folder_name}\n{names_str}", platform)
            else:
                self._log(f"转存失败：{result.get('error', '未知错误')}")
                self._notify(chat_id, f"❌ [115转存] 转存失败：{result.get('error', '未知错误')}", platform)

        except Exception as e:
            self._notify(chat_id, f"❌ [115转存] 异常：{e}", platform)

    def _do_transfer_sync(self, link, cid, folder_name, cookie):
        """同步执行转存，返回结果字典"""
        try:
            share_code, receive_code = self._extract_share_code(link)
            if not share_code:
                return {"status": "error", "message": "无法解析分享链接"}

            info_res = cloud115_client.get_share_snap(cookie, share_code, receive_code, timeout=15)
            if info_res.status_code != 200:
                return {"status": "error", "message": "获取分享信息失败"}

            info = info_res.json()
            if not info.get("state"):
                return {"status": "error", "message": f"分享已失效或需要访问码：{info.get('error', '未知错误')}"}

            # 获取文件列表
            file_list = info.get("data", {}).get("list", [])
            if not file_list:
                return {"status": "error", "message": "分享内容为空"}

            # 执行转存
            file_ids = [str(f.get("fid") or f.get("cid")) for f in file_list]
            share_snap_id = info.get("data", {}).get("shareinfo", {}).get("snap_id", "")

            transfer_res = cloud115_client.receive_share(cookie, {
                "share_code": share_code,
                "receive_code": receive_code,
                "snap_id": share_snap_id,
                "file_id": ",".join(file_ids),
                "cid": cid
            }, timeout=15)
            result = transfer_res.json()

            if result.get("state"):
                file_names = [f.get("n", "未知") for f in file_list]
                self._log(f"转存成功 → {folder_name}，{len(file_list)} 个文件")
                return {
                    "status": "success",
                    "message": f"转存成功，{len(file_list)} 个文件",
                    "files": file_names[:10],
                    "total": len(file_list)
                }
            else:
                self._log(f"转存失败：{result.get('error', '未知错误')}")
                return {"status": "error", "message": result.get('error', '转存失败')}

        except Exception as e:
            return {"status": "error", "message": f"转存异常: {str(e)}"}

    def _extract_share_code(self, link):
        """从链接中提取分享码和访问码"""
        receive_code = ""
        # 提取 password 参数（修复：# 后面的内容不应该被包含）
        pw_match = re.search(r'[?&]password=([^&#\s]+)', link)
        if pw_match:
            receive_code = pw_match.group(1)

        # 115://xxx 格式
        if link.startswith("115://"):
            try:
                import base64
                decoded = base64.b64decode(link[6:].split("|")[0]).decode('utf-8', errors='ignore')
                m = re.search(r'([a-zA-Z0-9]+)', decoded)
                return (m.group(1), receive_code) if m else (None, "")
            except:
                return (None, "")
        # https://115.com/s/xxxxx 或 https://115cdn.com/s/xxxxx 格式
        m = re.search(r'115(?:cdn)?\.com/s/([a-zA-Z0-9]+)', link)
        return (m.group(1), receive_code) if m else (None, "")

    def _notify(self, chat_id, text, platform, reply_markup=None):
        try:
            from app.domains.notifications.bot_service import bot
            if reply_markup:
                bot.send_message(chat_id, text, reply_markup=reply_markup, platform=platform)
            else:
                bot.send_message(chat_id, text, platform=platform)
        except:
            pass


# 临时缓存：存储待选择文件夹的链接
_transfer_cache = {}
# 临时缓存：存储待选择文件夹的离线链接
_offline_cache = {}


def handle_115_callback(data, chat_id, cq_id, platform):
    """处理文件夹选择回调"""
    # data 格式: p115_tf_{link_key}_{cid}
    parts = data.split("_")
    if len(parts) < 4:
        return False
    link_key = parts[2]
    cid = parts[3]

    links = _transfer_cache.pop(link_key, None)
    if not links:
        try:
            from app.domains.notifications.bot_service import bot
            bot.send_message(chat_id, "⚠️ 链接已过期，请重新发送", platform=platform)
        except:
            pass
        return True

    from app.plugins import get_plugin
    plugin = get_plugin("cloud115")
    if not plugin or not plugin.enabled:
        return True

    config = plugin._get_config()
    cookie = config.get("cookie", "")
    folders = plugin._parse_folders(config)
    folder_name = next((f.get("name", "未命名") for f in folders if str(f.get("cid")) == str(cid)), "未命名")

    for i, link in enumerate(links):
        if i > 0:
            time.sleep(3)
        threading.Thread(target=plugin._do_transfer, args=(link, cid, folder_name, cookie, chat_id, platform), daemon=True).start()
        if i > 0:
            time.sleep(1)  # 线程启动间隔

    return True


def handle_115_offline_callback(data, chat_id, cq_id, platform):
    """处理离线文件夹选择回调

    Args:
        data: callback_data，格式: p115_ol_{link_key}_{cid}
    """
    # data 格式: p115_ol_{link_key}_{cid}
    parts = data.split("_")
    if len(parts) < 4:
        return False
    link_key = parts[2]
    cid = parts[3]

    cache_data = _offline_cache.pop(link_key, None)
    if not cache_data:
        try:
            from app.domains.notifications.bot_service import bot
            bot.send_message(chat_id, "⚠️ 链接已过期，请重新发送", platform=platform)
        except:
            pass
        return True

    from app.plugins import get_plugin
    plugin = get_plugin("cloud115")
    if not plugin or not plugin.enabled:
        return True

    config = plugin._get_config()
    cookie = config.get("cookie", "")

    # 查找选择的文件夹信息
    offline_folders = plugin._parse_folders_string(config.get("offline_folders", ""))
    folder_info = None

    if cid == "0":
        # 选择了根目录
        folder_info = None
    else:
        # 在配置的离线文件夹中查找
        folder_info = next((f for f in offline_folders if str(f.get("cid")) == str(cid)), None)
        if not folder_info:
            # 如果没找到，创建一个
            folder_info = {"name": "未命名", "cid": cid}

    magnets = cache_data.get("magnets", [])
    ed2ks = cache_data.get("ed2ks", [])

    threading.Thread(target=plugin._process_offline, args=(magnets, ed2ks, folder_info, cookie, chat_id, platform), daemon=True).start()

    return True
