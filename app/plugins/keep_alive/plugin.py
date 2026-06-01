"""
保号规则插件 (Pro 专享)
设定每月最低播放时长/天数，不达标自动警告或禁用
"""
import time
import logging
import threading
import datetime
from fastapi import Request
from app.plugins.base import PluginBase
from app.domains.users.auth import is_admin_user  # 🔒 管理员鉴权
from app.infra.clients.media_server_client import media_api
from app.infra.clients.telegram_client import telegram_client
from app.infra.config.notification_settings import get_notify_bot_runtime_config
from app.infra.config.user_bot_settings import get_user_bot_token_or_empty
from app.plugins.keep_alive.keep_alive_dao import (
    count_keep_alive_disabled,
    count_keep_alive_unique_users,
    count_keep_alive_violations,
    ensure_keep_alive_violations_table,
    list_keep_alive_months,
    list_keep_alive_violations,
    save_keep_alive_violation,
    update_keep_alive_violation_disabled,
)
from app.dao.user_bot_dao import get_binding_by_emby_id
from app.dao.user_dao import list_permanent_user_expire_records
from app.domains.playback.stats_queries import get_user_play_summary

logger = logging.getLogger("uvicorn")


class KeepAlivePlugin(PluginBase):
    id = "keep_alive"
    name = "保号规则"
    description = "设定每月最低播放要求，不达标自动警告或禁用（Pro 专享）"
    icon = "fa-heart-pulse"
    icon_color = "from-rose-500 to-pink-500"
    version = "2.0.0"
    author = "EmbyPulse"

    def __init__(self):
        super().__init__()
        self._thread = None
        self._running = False
        self._setup_routes()
        self._init_db()

    def _init_db(self):
        """初始化违规记录表"""
        try:
            ensure_keep_alive_violations_table()
        except Exception as e:
            logger.error(f"[保号规则] 初始化数据库失败: {e}")

    def _setup_routes(self):
        """注册 API 路由"""

        @self.router.post("/check_now")
        async def api_check_now(request: Request):
            """立即执行检测"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            try:
                data = await request.json() if request.headers.get("content-type") == "application/json" else {}
                check_range = data.get("check_range", "last_month")
                result = self._do_check(manual=True, check_range=check_range)
                # 检查结果是否包含错误
                if isinstance(result, dict) and result.get("error"):
                    return {"status": "error", "message": result["error"]}
                return {"status": "success", "data": result}
            except Exception as e:
                logger.error(f"[保号规则] 立即检测失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.get("/violations")
        def api_get_violations(request: Request, year_month: str = None, page: int = 1, limit: int = 20):
            """获取历史违规记录"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            try:
                return self._get_violations(year_month, page, limit)
            except Exception as e:
                logger.error(f"[保号规则] 获取违规记录失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.post("/unban")
        async def api_unban_user(request: Request):
            """解禁用户"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            try:
                data = await request.json()
                user_id = data.get("user_id")
                violation_id = data.get("violation_id")
                if not user_id:
                    return {"status": "error", "message": "缺少用户ID"}
                return self._unban_user(user_id, violation_id)
            except Exception as e:
                logger.error(f"[保号规则] 解禁用户失败: {e}")
                return {"status": "error", "message": str(e)}

        @self.router.get("/stats")
        def api_get_stats(request: Request):
            """获取统计信息"""
            if not request.session.get("user"):
                return {"status": "error", "message": "未登录"}
            if not is_admin_user(request):
                return {"status": "error", "message": "需要管理员权限"}
            try:
                return self._get_stats()
            except Exception as e:
                logger.error(f"[保号规则] 获取统计失败: {e}")
                return {"status": "error", "message": str(e)}

    def on_enable(self):
        self._running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True)
        self._thread.start()
        logger.info("🔌 [保号规则] 插件已启用，后台巡检线程已启动")

    def on_disable(self):
        self._running = False
        logger.info("🔌 [保号规则] 插件已禁用")

    def get_config_schema(self):
        return [
            {"key": "check_range", "label": "检测范围", "type": "select", "options": [
                {"value": "last_month", "label": "📅 上个月（完整周期）"},
                {"value": "this_month", "label": "📆 本月截至目前"},
            ], "hint": "选择检测的时间范围：上个月检测完整周期，本月检测截至当前时间"},
            {"key": "min_hours", "label": "每月最低播放时长（小时）", "type": "number", "placeholder": "2", "hint": "每月至少播放多少小时，默认2小时"},
            {"key": "min_days", "label": "每月最低活跃天数", "type": "number", "placeholder": "0", "hint": "每月至少有多少天有播放记录，0表示不限制"},
            {"key": "action", "label": "不达标处理方式", "type": "select", "options": [
                {"value": "warn", "label": "⚠️ 仅通知管理员"},
                {"value": "notify_user", "label": "📢 通知用户+管理员"},
                {"value": "disable", "label": "🚫 自动禁用账号"},
            ]},
            {"key": "whitelist", "label": "免检白名单", "type": "textarea", "placeholder": "每行一个用户名，白名单内的用户不受保号规则约束", "hint": "填写 Emby 用户名，每行一个"},
            {"key": "auto_whitelist_permanent", "label": "自动白名单永久用户", "type": "toggle", "hint": "开启后，过期时间为2099年、3000年或包含'永久'的用户自动跳过检测", "default": "1"},
            {"key": "schedule_mode", "label": "调度模式", "type": "select", "options": [
                {"value": "monthly", "label": "📅 每月固定日期"},
                {"value": "cron", "label": "⏰ Cron表达式（高级）"},
            ], "hint": "选择检查任务的调度方式"},
            {"key": "check_day", "label": "每月检查日", "type": "number", "placeholder": "1", "hint": "每月几号执行检查（1-31），默认1号。如果该月没有这一天，则取当月最后一天"},
            {"key": "check_hour", "label": "检查时间（小时）", "type": "number", "placeholder": "9", "hint": "几点执行检查（0-23），默认9点"},
            {"key": "cron_expression", "label": "Cron表达式", "type": "text", "placeholder": "0 9 1 * *", "hint": "Linux Cron格式：分 时 日 月 周。例如：0 9 1 * * 表示每月1号9点；0 9 * * 1 表示每周一9点"},
            {"key": "notify_enabled", "label": "启用通知", "type": "toggle", "hint": "开启后，插件运行状态会发送到全局通知"},
        ]

    def _get_config(self):
        from app.plugins import get_plugin_config
        return get_plugin_config(self.id)

    def _is_pro(self):
        return True

    def _log(self, msg, level="info"):
        """记录日志（兼容旧代码）"""
        self.log(msg, level=level)

    def _check_loop(self):
        """检查循环 - 支持两种调度模式"""
        time.sleep(120)
        last_check_minute = None  # 用于防止同一分钟重复执行

        while self._running and self._enabled:
            if not self._is_pro():
                print("[保号规则] 非 Pro 用户，跳过巡检")
                time.sleep(3600)
                continue

            try:
                config = self._get_config()
                schedule_mode = config.get("schedule_mode") or "monthly"
                now = datetime.datetime.now()
                current_minute = now.strftime("%Y-%m-%d %H:%M")

                should_check = False

                if schedule_mode == "cron":
                    # Cron 表达式模式
                    should_check = self._check_cron_trigger(config, now, last_check_minute)
                else:
                    # 每月固定日期模式（默认）
                    should_check = self._check_monthly_trigger(config, now, last_check_minute)

                if should_check:
                    last_check_minute = current_minute
                    self._do_check()

            except Exception as e:
                logger.error(f"[保号规则] 巡检异常: {e}")

            # 每小时检查一次（在整点判断是否需要执行）
            time.sleep(3600)

    def _check_monthly_trigger(self, config, now, last_check_minute):
        """检查是否到达每月固定日期的触发时间"""
        current_minute = now.strftime("%Y-%m-%d %H:%M")
        if current_minute == last_check_minute:
            return False

        check_day = int(config.get("check_day") or 1)
        check_hour = int(config.get("check_hour") or 9)

        # 处理日期超过当月天数的情况（如31号在2月）
        import calendar
        _, last_day_of_month = calendar.monthrange(now.year, now.month)
        actual_check_day = min(check_day, last_day_of_month)

        # 检查是否到达指定日期和小时
        if now.day == actual_check_day and now.hour == check_hour:
            return True
        return False

    def _check_cron_trigger(self, config, now, last_check_minute):
        """检查是否到达 Cron 表达式的触发时间"""
        current_minute = now.strftime("%Y-%m-%d %H:%M")
        if current_minute == last_check_minute:
            return False

        cron_expr = config.get("cron_expression") or "0 9 1 * *"
        try:
            return self._match_cron(cron_expr, now)
        except Exception as e:
            logger.error(f"[保号规则] Cron表达式解析失败: {e}")
            return False

    def _match_cron(self, expression, dt):
        """简单的 Cron 表达式匹配（不支持特殊字符如 / - , L W）"""
        parts = expression.strip().split()
        if len(parts) != 5:
            return False

        minute, hour, day, month, weekday = parts

        # 检查分钟（必须是整点，即 0）
        if minute != '*' and int(minute) != dt.minute:
            return False

        # 检查小时
        if hour != '*' and int(hour) != dt.hour:
            return False

        # 检查日期
        if day != '*':
            if day == 'L':  # 最后一天
                import calendar
                _, last_day = calendar.monthrange(dt.year, dt.month)
                if dt.day != last_day:
                    return False
            elif int(day) != dt.day:
                return False

        # 检查月份
        if month != '*' and int(month) != dt.month:
            return False

        # 检查星期（0=周日，6=周六）
        if weekday != '*':
            # Python 的 weekday(): 0=周一，6=周日
            # Cron 的 weekday: 0=周日，6=周六
            cron_weekday = dt.weekday() + 1
            if cron_weekday == 7:
                cron_weekday = 0
            if int(weekday) != cron_weekday:
                return False

        return True

    def _do_check(self, manual=False, check_range=None):
        """执行检测
        Args:
            manual: 是否为手动触发
            check_range: 手动指定检测范围，覆盖配置 (last_month / this_month)
        Returns:
            手动触发时返回检测结果字典
        """
        self._log(f"🔍 开始执行保号检测 (手动触发: {manual}, 检测范围: {check_range})")
        config = self._get_config()
        # 手动触发的 check_range 优先，否则使用配置
        if check_range is None:
            check_range = config.get("check_range") or "last_month"
        min_hours = float(config.get("min_hours") or 2)
        min_days = int(config.get("min_days") or 0)
        action = config.get("action") or "warn"
        whitelist_raw = config.get("whitelist") or ""
        whitelist = set(name.strip() for name in whitelist_raw.split("\n") if name.strip())
        self._log(f"📋 检测配置: 最低{min_hours}小时/{min_days}天, 处理方式: {action}, 白名单: {len(whitelist)}人")

        # 自动添加永久有效用户到白名单
        # 永久用户定义：expire_date 为 NULL 或空字符串，或过期时间在 2099 年之后
        auto_whitelist_enabled = config.get("auto_whitelist_permanent")
        self._log(f"🔍 自动白名单永久用户配置: {auto_whitelist_enabled} (类型: {type(auto_whitelist_enabled).__name__})")
        # 兼容多种配置值格式: "1", 1, True, "true", "on"
        auto_whitelist_enabled = str(auto_whitelist_enabled).lower() in ["1", "true", "on", "yes"] if auto_whitelist_enabled is not None else True
        self._log(f"🔍 自动白名单永久用户启用: {auto_whitelist_enabled}")

        permanent_users = set()
        if auto_whitelist_enabled:
            try:
                rows = list_permanent_user_expire_records()
                self._log(f"🔍 查询到 {len(rows)} 条永久用户记录")
                for row in rows:
                    if row["user_id"]:
                        permanent_users.add(row["user_id"])
                        if len(permanent_users) <= 10:  # 只打印前10个，避免日志过多
                            exp_display = row["expire_date"] if row["expire_date"] else "永久"
                            self._log(f"💎 永久用户白名单: {row['user_id']} (过期时间: {exp_display})")
                if permanent_users:
                    self._log(f"💎 自动白名单: 共检测到 {len(permanent_users)} 个永久有效用户")
                else:
                    self._log(f"💎 自动白名单: 未检测到永久有效用户")
            except Exception as e:
                self._log(f"❌ 查询永久用户失败: {e}", level="error")
                import traceback
                logger.error(traceback.format_exc())

        if not media_api.host or not media_api.api_key:
            if manual:
                return {"error": "未配置 Emby 主机或 API Key"}
            return

        # 获取所有 Emby 用户
        try:
            res = media_api.get("/Users", timeout=10)
            if res.status_code != 200:
                if manual:
                    return {"error": f"获取用户列表失败: HTTP {res.status_code}"}
                return
            emby_users = res.json()
            self._log(f"🔍 获取到 {len(emby_users)} 个 Emby 用户")
        except Exception as e:
            self._log(f"❌ 获取用户列表异常: {e}", level="error")
            if manual:
                return {"error": f"获取用户列表异常: {str(e)}"}
            return

        # 确定检查的时间范围
        today = datetime.date.today()

        if check_range == "this_month":
            # 检测本月截至目前
            first_of_month = today.replace(day=1)
            start_str = first_of_month.strftime("%Y-%m-%d")
            end_str = (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")  # 到明天0点（包含今天）
            year_month = first_of_month.strftime("%Y-%m")
            range_label = "本月"
        else:
            # 检测上个月（默认）
            first_of_month = today.replace(day=1)
            last_month_end = first_of_month - datetime.timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            start_str = last_month_start.strftime("%Y-%m-%d")
            end_str = first_of_month.strftime("%Y-%m-%d")
            year_month = last_month_start.strftime("%Y-%m")
            range_label = "上月"

        self._log(f"🔍 检测时间范围: {start_str} ~ {end_str} ({range_label})")

        violations = []
        disabled_users = []
        skipped_permanent = 0  # 统计跳过的永久用户数
        skipped_whitelist = 0  # 统计跳过的白名单用户数
        checked_count = 0  # 统计实际检测的用户数

        for user in emby_users:
            uid = user.get("Id")
            uname = user.get("Name", "未知")
            is_admin = user.get("Policy", {}).get("IsAdministrator", False)
            is_disabled = user.get("Policy", {}).get("IsDisabled", False)
            if is_admin or is_disabled: continue

            # 手动配置的白名单免检
            if uname in whitelist:
                skipped_whitelist += 1
                continue

            # 永久有效用户自动跳过
            if uid in permanent_users:
                skipped_permanent += 1
                continue

            checked_count += 1

            # 查询上月播放数据
            try:
                row = get_user_play_summary(uid, start_str, end_str)
            except Exception as e:
                self._log(f"❌ 查询用户 {uname} 播放数据失败: {e}", level="error")
                continue

            total_dur = (row['total_dur'] or 0) if row else 0
            active_days = (row['active_days'] or 0) if row else 0
            total_hours = round(total_dur / 3600, 1)

            failed_hours = min_hours > 0 and total_hours < min_hours
            failed_days = min_days > 0 and active_days < min_days

            if failed_hours or failed_days:
                reason_parts = []
                if failed_hours: reason_parts.append(f"播放{total_hours}h < 要求{min_hours}h")
                if failed_days: reason_parts.append(f"活跃{active_days}天 < 要求{min_days}天")
                reason = "，".join(reason_parts)

                violation = {
                    "uid": uid,
                    "name": uname,
                    "reason": reason,
                    "hours": total_hours,
                    "days": active_days,
                    "min_hours": min_hours,
                    "min_days": min_days,
                    "action": action
                }
                violations.append(violation)

                # 自动禁用
                was_disabled = False
                if action == "disable":
                    try:
                        media_api.post(f"/Users/{uid}/Policy", json={"IsDisabled": True}, timeout=5)
                        was_disabled = True
                        disabled_users.append(uname)
                        violation["disabled"] = True
                    except Exception as e:
                        logger.error(f"[保号规则] 禁用用户 {uname} 失败: {e}")
                        violation["disabled"] = False

                # 保存到历史记录
                self._save_violation(violation, year_month, was_disabled)

        # 输出检测统计
        self._log(f"🔍 检测完成: 检查 {checked_count} 人, 白名单跳过 {skipped_whitelist} 人, 永久用户跳过 {skipped_permanent} 人, 违规 {len(violations)} 人")

        # 生成报告并发送通知（无论手动还是自动都发送）
        self._generate_report(violations, action, year_month, start_str, end_str, range_label, skipped_permanent)

        if manual:
            return {
                "year_month": year_month,
                "period": f"{start_str} ~ {end_str}",
                "range_label": range_label,
                "total_users": len(emby_users),
                "checked_count": checked_count,
                "violations_count": len(violations),
                "action": action,
                "disabled_count": len(disabled_users),
                "skipped_permanent": skipped_permanent,
                "skipped_whitelist": skipped_whitelist,
                "whitelist_count": len(whitelist),
                "violations": violations
            }

    def _save_violation(self, violation, year_month, was_disabled):
        """保存违规记录到数据库"""
        try:
            save_keep_alive_violation(
                violation["uid"],
                violation["name"],
                year_month,
                violation["hours"],
                violation["days"],
                violation["min_hours"],
                violation["min_days"],
                violation["action"],
                was_disabled,
            )
        except Exception as e:
            logger.error(f"[保号规则] 保存违规记录失败: {e}")

    def _generate_report(self, violations, action, year_month, start_str, end_str, range_label="上月", skipped_permanent=0):
        """生成并发送报告"""
        import html  # 用于 HTML 转义

        if not violations:
            skip_msg = f"，跳过 {skipped_permanent} 个永久用户" if skipped_permanent > 0 else ""
            self._log(f"✅ {range_label}({start_str}~{end_str})所有用户均达标{skip_msg}")
            return

        month_str = year_month.replace("-", "年") + "月"
        report_lines = [f"📋 <b>保号规则巡检报告 ({range_label} {month_str})</b>\n"]
        report_lines.append(f"⚠️ 共 {len(violations)} 人未达标\n")
        if skipped_permanent > 0:
            report_lines.append(f"💎 已自动跳过 {skipped_permanent} 个永久有效用户\n")

        for v in violations:
            status = "🚫 已禁用" if action == "disable" else "⚠️ 警告"
            # HTML 转义用户名和原因，避免解析错误
            safe_name = html.escape(v['name'])
            safe_reason = html.escape(v['reason'])
            report_lines.append(f"👤 <b>{safe_name}</b> — {status}\n   {safe_reason}")

        report_msg = "\n".join(report_lines)

        # 通知管理员
        try:
            notify_cfg = get_notify_bot_runtime_config()
            tg_token = notify_cfg["tg_bot_token"]
            tg_chat_id = notify_cfg["tg_chat_id"]
            wecom_corpid = notify_cfg["wecom_corpid"]

            self._log(f"📢 准备发送通知: tg_token={'已配置' if tg_token else '未配置'}, tg_chat_id={tg_chat_id or '未配置'}, wecom={'已配置' if wecom_corpid else '未配置'}")

            if not tg_token and not wecom_corpid:
                self._log(f"⚠️ 未配置任何通知渠道 (tg_bot_token 或企业微信)", level="warning")
            else:
                # 使用 bot.send_message 统一发送，让 bot_service 处理 TG 和企业微信
                from app.services.bot_service import bot
                bot.send_message("sys_notify", report_msg, platform="all")
                self._log(f"✅ 管理员通知已发送")
        except Exception as e:
            logger.error(f"[保号规则] 通知管理员失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

        # 通知用户
        if action == "notify_user":
            notify_count = 0
            for v in violations:
                if self._notify_user(v['uid'], v['reason'], month_str, range_label):
                    notify_count += 1
            self._log(f"📢 已通知 {notify_count}/{len(violations)} 个用户")

        action_text = {"warn": "仅通知", "notify_user": "通知用户", "disable": "自动禁用"}
        self._log(f"巡检完成({range_label} {month_str}): {len(violations)}人未达标，处理方式: {action_text.get(action, action)}")

    def _get_violations(self, year_month=None, page=1, limit=20):
        """获取历史违规记录"""
        try:
            # 确保表存在
            self._init_db()

            # 获取所有月份列表
            months = list_keep_alive_months()
            month_list = [m['year_month'] for m in (months or [])]

            # 如果没有指定月份，使用最新的
            if not year_month and month_list:
                year_month = month_list[0]

            # 查询该月份的违规记录
            if year_month:
                offset = (page - 1) * limit
                rows = list_keep_alive_violations(year_month, limit, offset)
                total = count_keep_alive_violations(year_month)
            else:
                rows = []
                total = 0

            # 获取 Emby 用户当前状态（用于显示是否被禁用）
            emby_user_status = {}
            try:
                if media_api.host and media_api.api_key:
                    res = media_api.get("/Users", timeout=10)
                    if res.status_code == 200:
                        for u in res.json():
                            emby_user_status[u.get("Id")] = u.get("Policy", {}).get("IsDisabled", False)
            except Exception:
                pass

            # 格式化数据
            violations = []
            for r in (rows or []):
                user_id = r['user_id']
                violations.append({
                    "id": r['id'],
                    "user_id": user_id,
                    "user_name": r['user_name'],
                    "year_month": r['year_month'],
                    "hours": r['hours'],
                    "days": r['days'],
                    "min_hours": r['min_hours'],
                    "min_days": r['min_days'],
                    "action": r['action'],
                    "disabled": bool(r['disabled']),
                    "currently_disabled": emby_user_status.get(user_id, False),
                    "created_at": r['created_at']
                })

            return {
                "status": "success",
                "data": {
                    "violations": violations,
                    "year_month": year_month or "",
                    "month_list": month_list,
                    "pagination": {
                        "page": page,
                        "limit": limit,
                        "total": total,
                        "total_pages": max(1, (total + limit - 1) // limit)
                    }
                }
            }
        except Exception as e:
            logger.error(f"[保号规则] 获取违规记录失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}

    def _unban_user(self, user_id, violation_id=None):
        """解禁用户"""
        if not media_api.host or not media_api.api_key:
            return {"status": "error", "message": "未配置 Emby"}

        try:
            # 调用 Emby API 解禁
            res = media_api.post(f"/Users/{user_id}/Policy", json={"IsDisabled": False}, timeout=5)
            if res.status_code != 200 and res.status_code != 204:
                return {"status": "error", "message": f"Emby API 返回 HTTP {res.status_code}"}

            # 更新违规记录状态
            if violation_id:
                update_keep_alive_violation_disabled(violation_id, False)

            # 获取用户名
            user_res = media_api.get(f"/Users/{user_id}", timeout=5)
            user_name = "未知用户"
            if user_res.status_code == 200:
                user_name = user_res.json().get("Name", "未知用户")

            self._log(f"✅ 用户 {user_name} 已被管理员解禁")
            return {"status": "success", "message": f"用户 {user_name} 已解禁"}

        except Exception as e:
            logger.error(f"[保号规则] 解禁用户失败: {e}")
            return {"status": "error", "message": str(e)}

    def _get_stats(self):
        """获取统计信息"""
        try:
            # 确保表存在
            self._init_db()

            # 总违规次数
            total_violations = count_keep_alive_violations()

            # 被禁用次数
            total_disabled = count_keep_alive_disabled()

            # 本月违规数
            current_month = datetime.date.today().strftime("%Y-%m")
            month_violations = count_keep_alive_violations(current_month)

            # 违规用户数（去重）
            unique_users = count_keep_alive_unique_users()

            return {
                "status": "success",
                "data": {
                    "total_violations": total_violations,
                    "total_disabled": total_disabled,
                    "month_violations": month_violations,
                    "unique_users": unique_users,
                    "current_month": current_month
                }
            }
        except Exception as e:
            logger.error(f"[保号规则] 获取统计失败: {e}")
            return {"status": "error", "message": str(e)}

    def _notify_user(self, user_id, reason, month_str, range_label="上月"):
        """通过用户机器人通知用户，返回是否成功"""
        import html  # 用于 HTML 转义

        try:
            # 检查用户机器人是否启用
            user_bot_token = get_user_bot_token_or_empty()
            if not user_bot_token:
                self._log(f"⚠️ 未配置用户机器人 (tg_user_bot_token)，跳过用户通知", level="warning")
                return False

            binding = get_binding_by_emby_id(user_id)

            if not binding:
                self._log(f"📢 用户 {user_id} 未绑定 Telegram（非TG注册用户），跳过通知")
                return False

            if not binding.get("tg_user_id"):
                self._log(f"📢 用户 {user_id} 的 TG 绑定信息为空，跳过通知")
                return False

            chat_id = str(binding["tg_user_id"])
            emby_name = binding.get("emby_username") or user_id
            self._log(f"📢 尝试通知用户 {emby_name} (TG chat_id: {chat_id})")

            # HTML 转义原因，避免解析错误
            safe_reason = html.escape(reason)
            msg = (f"⚠️ <b>保号提醒 ({range_label} {month_str})</b>\n\n"
                   f"您的使用情况未达到保号要求：\n{safe_reason}\n\n"
                   f"请增加使用频率，避免账号被回收。")

            # 直接使用 Telegram API 发送消息
            from app.utils.proxy_helper import get_safe_proxies
            proxies = get_safe_proxies()
            data = {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}

            res = telegram_client.send_message(user_bot_token, data, proxies=proxies, timeout=15)
            if res.status_code == 200:
                self._log(f"✅ 已通知用户 {emby_name} (TG: {chat_id})")
                return True
            else:
                logger.error(f"[保号规则] 通知用户失败: HTTP {res.status_code} - {res.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"[保号规则] 通知用户异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
