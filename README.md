# 🎬 EmbyPulse-Pro（映迹专业版）

<div align="center">
  <img src="static/img/logo-light.png" alt="EmbyPulse-Pro Logo" width="200" />

  <h3>Emby 服务器的专业级管理中枢：影巢集成 · 风险管控 · 智能运维</h3>

  <p>
    <img src="https://img.shields.io/badge/version-1.4.5-2EA44F?style=flat-square" alt="Version" />
    <img src="https://img.shields.io/badge/python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
    <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="License" />
  </p>

  <a href="https://t.me/Emby_Pulse">
    <img src="https://img.shields.io/badge/Telegram-加入交流群-2CA5E0?style=for-the-badge&logo=telegram" alt="Telegram Group">
  </a>
  <br/>
  <p align="center">
    <a href="#-pro版独占特性"><img src="https://img.shields.io/badge/Pro独占特性-FF6B6B?style=for-the-badge&labelColor=CC5555" alt="Pro独占特性" /></a>
    <a href="#-核心功能"><img src="https://img.shields.io/badge/核心功能-6B7280?style=for-the-badge&labelColor=4B5563" alt="核心功能" /></a>
    <a href="#-插件系统"><img src="https://img.shields.io/badge/插件系统-8B5CF6?style=for-the-badge&labelColor=6D28D9" alt="插件系统" /></a>
    <a href="#-快速部署"><img src="https://img.shields.io/badge/快速部署-6F6AB1?style=for-the-badge&labelColor=4F4A8C" alt="快速部署" /></a>
    <a href="#️-配置说明"><img src="https://img.shields.io/badge/配置说明-5F8F6D?style=for-the-badge&labelColor=3F6B4D" alt="配置说明" /></a>
  </p>
</div>

## 🔥 Pro版独占特性

> 💡 **Pro 版** 是 EmbyPulse 的专业增强版，在保留原版全部功能的基础上，新增以下独占能力：

### 🎬 影巢资源集成
- **全局搜索**：本地库 + 影巢资源一键切换搜索
- **TMDB 联动**：自动匹配海报、背景图、简介信息
- **一键转存**：支持直接转存到 115 网盘指定目录
- **拼音穿透**：本地搜索支持拼音首字母快速定位

### 🛡️ 风险管控引擎
- **并发检测**：实时监控多设备并发播放，自定义阈值
- **违规拦截**：自动识别异常账号，支持警告/封禁/踢下线
- **VIP 豁免**：VIP 用户可跳过风控检测
- **执法记录**：完整的封禁/解封操作日志追溯

### 💎 积分系统
- **每日签到**：随机积分奖励，激励用户活跃
- **积分商城**：兑换账号续期、邀请码等
- **消费扣费**：求片扣费、自定义消费场景

### 🎨 自定义通知模板
- **多种风格**：动漫风、幽默风、简约风等预设模板
- **完全自定义**：支持所有变量字段自由组合
- **随机文案**：同类型通知多条模板随机切换

### 🔄 智能合集
- **TMDB 热门**：自动同步 TMDB 热门/高分电影、剧集
- **正在热播**：追踪正在连载中的剧集
- **自动更新**：定时同步，保持合集新鲜度

### 📋 保号规则
- **播放要求**：设置每月最低播放时长/天数
- **自动处理**：不达标自动警告或禁用账号
- **VIP 豁免**：VIP 用户可豁免保号规则

### 📧 邮件系统
- **邮箱验证**：注册时邮箱验证码确认
- **密码重置**：通过邮件重置密码
- **系统通知**：重要事件邮件推送

### 🧹 媒体去重
- **智能扫描**：识别重复的电影/剧集资源
- **多维对比**：分辨率、码率、编码、HDR 等
- **推荐删除**：自动标记低质量资源

## ✨ 核心功能

### 📊 1. 全景仪表盘
- 实时并发播放监控，IP 归属地精确显示
- 资源概览：电影、剧集、单集总数统计
- 播放趋势：ECharts 动态图表，按天/周/月分析
- 系统状态：CPU、内存、存储实时监控

### 🔍 2. 缺集管理
- **全库扫描**：智能比对 Emby 库存与 TMDB 数据
- **精准定位**：识别已上线但库内缺失的集数
- **MoviePilot 联动**：一键搜索，智能匹配版本
- **下载截胡**：推送整季包时自动剔除已有集数
- **状态同步**：入库后自动核销，焦点唤醒刷新

### 📅 3. 追剧日历
- 全球热播剧集更新时间表
- 红绿灯状态：🟢 已入库 / 🔴 缺失
- 一键跳转播放或复制搜索指令

### 🎬 4. 求片系统
- 用户提交电影/剧集/季度请求
- 完整状态链路：待处理 → 已下载 → 已入库 / 已拒绝
- 入库自动闭环，通知用户
- 机器人协同：Telegram 求片交互

### 👤 5. 用户中心
- 账号信息、到期时间、VIP 标识
- 用户画像：成就勋章、观影偏好分析
- 行为追溯：播放历史、活跃趋势

### 🕵️ 6. 数据洞察
- **用户画像**：深夜修仙、全平台制霸等趣味成就
- **入驻溯源**：精确显示账号注册天数
- **画质审计**：4K/HDR/杜比视界占比分析
- **低质筛选**：自动标记 SD/480P 资源

### 🎨 7. 映迹工坊
- 多维报表：日报、周报、月报、年度总结
- 精美主题：黑金、赛博、极光、落日等风格
- 一键生成长图，支持 Telegram 自动推送

### 🎟️ 8. 邀请注册
- 生成邀请链接，设置有效期
- 用户自助注册，无需管理员干预
- 账号自动到期、批量续期管理

### 🤖 9. Telegram 机器人
- **实时推送**：播放开始/停止、入库通知
- **风控告警**：并发违规、异常登录提醒
- **交互指令**：`/stats` 统计、`/search` 搜片、`/check` 诊断
- **客户端拦截**：自动踢出黑名单客户端

### 🛠️ 10. 系统运维
- **任务管理**：可视化管理 Emby 计划任务
- **实时日志**：网页端查看系统日志
- **数据库工具**：完整性检测、一键修复、备份恢复
- **系统诊断**：配置检查、连接测试

### 📜 11. 播放历史
- 全站用户播放流水记录
- IP 归属地精确查询（IPv4/IPv6）
- 用户头像、设备信息展示

## 🧩 插件系统

Pro 版内置多个功能插件：

| 插件 | 功能 | 说明 |
|------|------|------|
| **影巢资源** | 资源搜索 + 115 转存 | 全局搜索集成，一键转存 |
| **115网盘** | 链接自动转存 | 管理员发送链接自动转存 |
| **保号规则** | 播放时长达标检测 | Pro 专享 |
| **通知模板** | 自定义通知风格 | 动漫风、幽默风等 |
| **智能合集** | TMDB 热门合集 | Pro 专享 |

## 🚀 快速部署

> 本仓库镜像通过 GitHub Actions 自动构建并发布到 **GHCR**（GitHub Container Registry），支持 `linux/amd64` 与 `linux/arm64`。

**镜像地址：**

| 镜像 | 说明 |
|------|------|
| `ghcr.io/amlkiller/emby-pulse:latest` | 本仓库（amlkiller）最新稳定版 |
| `ghcr.io/amlkiller/emby-pulse:1.4.5` | 锁定具体版本 |
| `zeyu8023/embypulse-pro:latest` | 上游官方镜像 |

### 端口说明

EmbyPulse-Pro 物理隔离了两个端口，分别承载不同角色：

| 端口 | 角色 | 说明 |
|------|------|------|
| `10307` | **管理端口（admin portal）** | 主仪表盘、运维工具、所有管理 API |
| `10308` | **用户端口（user portal）** | 仅对邀请/求片等公开页面开放，物理隔离 |

> 如只对外开放注册 / 求片，**只暴露 10308 即可**，10307 留在内网，安全性更高。

### Docker Compose（推荐）

仓库根目录已提供完整 `docker-compose.yml` 模板，直接修改卷路径与环境变量即可：

```yaml
version: '3.8'
services:
  embypulse-pro:
    image: ghcr.io/amlkiller/emby-pulse:latest
    container_name: embypulse-pro
    restart: unless-stopped
    ports:
      - "10307:10307"   # 管理端口（建议仅内网暴露）
      - "10308:10308"   # 用户端口（可对外）
    volumes:
      - ./config:/workspace/config      # 配置文件目录
      - ./data:/workspace/data          # 数据库与持久化目录
      # - /path/to/emby/data:/emby-data  # API 模式下可不挂载数据库
    environment:
      - TZ=Asia/Shanghai
      - EMBY_HOST=http://192.168.x.x:8096   # 必填：用于登录校验 Emby 管理员账号
      # - PORT=10307                 # 管理端口（默认 10307）
      # - REQUEST_PORT=10308         # 用户端口（默认 10308）
      # - DB_PATH=/emby-data/playback_reporting.db  # 本地模式必填
      # - CORS_ORIGINS=https://your.domain          # 不设置默认拒绝跨域
      # - FORCE_MIGRATE=1            # 强制迁移系统数据库
    # 推荐使用 env_file 注入 EMBY_API_KEY / TG_BOT_TOKEN / TMDB_API_KEY / WEBHOOK_TOKEN
    # env_file:
    #   - ./.env
```

> ⚠️ **反向代理 / CSRF 必读**：1.4.x 起所有 POST/PUT/DELETE/PATCH 请求都会进行严格的同源校验
> （`app/core/csrf_middleware.py`）。如果你通过 Nginx / Caddy / Traefik 反代访问，**必须**
> 让反代下发以下头部，否则浏览器的 `Origin` / `Referer` 会与容器内部 `base_url` 不一致，
> 提交任何表单都会收到 `403 CSRF 验证失败：Origin 不匹配`：
>
> - `X-Forwarded-Proto`：`http` 或 `https`（必须与浏览器栏一致）
> - `X-Forwarded-Host`：用户访问的真实域名（可含端口）
> - `X-Forwarded-Port`：非默认端口时务必下发
>
> 示例（Nginx）：
> ```nginx
> proxy_set_header Host              $host;
> proxy_set_header X-Forwarded-Proto $scheme;
> proxy_set_header X-Forwarded-Host  $host;
> proxy_set_header X-Forwarded-Port  $server_port;
> ```
>
> 直连访问（`http://ip:10307`、`http://ip:10308`）无需任何额外配置。

### 环境变量说明

| 变量 | 说明 | 默认值 | 必填 |
|------|------|--------|------|
| `TZ` | 时区设置 | `Asia/Shanghai` | 推荐 |
| `PORT` | 管理端口 | `10307` | 可选 |
| `REQUEST_PORT` | 用户端口 | `10308` | 可选 |
| `DB_PATH` | Playback Reporting 数据库路径 | - | 本地模式必填 |
| `EMBY_HOST` | Emby 服务器 URL（可后台填写） | - | 推荐 |
| `EMBY_API_KEY` | Emby API Key（敏感字段，建议环境变量） | - | 推荐 |
| `SECRET_KEY` | 会话加密密钥（未设置时自动生成） | - | 可选 |
| `CORS_ORIGINS` | 允许跨域来源，逗号分隔；未设置即拒绝所有跨域 | - | 可选 |
| `FORCE_MIGRATE` | 强制迁移系统数据库 | `0` | 可选 |
| `AUTO_MIGRATE_DB` | 启动时自动迁移 | `0` | 可选 |

> 🔐 **安全提示**：`EMBY_API_KEY`、`TG_BOT_TOKEN` 等敏感字段优先从环境变量读取；若通过环境变量设置，将自动从磁盘配置文件中清除。

### 端口配置说明

**方式一：使用 ports 映射（推荐）**
```yaml
ports:
  - "8080:10307"   # 主机 8080 → 容器 10307（管理）
  - "8081:10308"   # 主机 8081 → 容器 10308（用户）
```

**方式二：使用 network_mode: host**
```yaml
network_mode: host  # 直接使用主机网络，无需端口映射
# 此时服务监听 PORT / REQUEST_PORT 指定的端口
```

### 数据库模式说明

| 模式 | 配置 | 适用场景 |
|------|------|----------|
| **API 模式** | 不设置 `DB_PATH` | 极空间、云服务器、无法挂载数据库 |
| **本地模式** | 设置 `DB_PATH` | 本地 Docker、可挂载 Emby 数据目录 |

### 强制迁移说明

当系统数据库结构发生变化时，可通过设置 `FORCE_MIGRATE=1` 强制执行数据库迁移：

```yaml
environment:
  - FORCE_MIGRATE=1   # 启动时强制迁移
```

> ⚠️ 迁移会自动备份原数据库，但建议在操作前手动备份 `data/` 目录

## ⚙️ 配置说明

### Emby 基础配置

| 配置项 | 说明 |
|--------|------|
| `emby_host` | Emby 服务器地址 |
| `emby_api_key` | Emby API Key |
| `webhook_token` | Webhook 安全校验令牌 |
| `emby_public_url` | 对外访问 Emby 的公网地址 |

### 影巢配置（Pro独占）

| 配置项 | 说明 |
|--------|------|
| `hdhive_api_key` | 影巢 API Key，从 hdhive.com 获取 |

### 风控配置（Pro独占）

| 配置项 | 说明 |
|--------|------|
| `risk_max_concurrent` | 最大并发数限制 |
| `risk_action` | 违规处理方式：warn_only / warn_user / auto_ban |
| `risk_vip_exempt` | VIP 用户豁免开关 |

### Telegram 配置

| 配置项 | 说明 |
|--------|------|
| `tg_bot_token` | Telegram Bot Token |
| `tg_chat_id` | 推送目标聊天 ID |
| `proxy_url` | 网络代理（可选） |

### TMDB 配置

| 配置项 | 说明 |
|--------|------|
| `tmdb_api_key` | TMDB API Key，用于缺集扫描、合集同步 |

### MoviePilot 配置

| 配置项 | 说明 |
|--------|------|
| `moviepilot_url` | MoviePilot 服务地址 |
| `moviepilot_token` | MoviePilot API Token |

### 下载器配置（用于截胡）

| 配置项 | 说明 |
|--------|------|
| `client_type` | 下载器类型：qb / tr |
| `client_url` | 下载器地址 |
| `client_user` | 下载器账号 |
| `client_pass` | 下载器密码 |

## ❓ 常见问题

### Q: 是否必须安装 Playback Reporting 插件？

A: 是的。无论使用本地模式还是 API 模式，Emby 都必须安装此官方插件以生成播放历史数据。

### Q: API 模式和本地模式有什么区别？

A:
- **本地模式**：直接读取数据库文件，性能最高，适合能挂载目录的 Docker 环境
- **API 模式**：通过 API 穿透查询，部署最简单，适合无法直接映射文件的环境

### Q: Pro 版与普通版有什么区别？

A: Pro 版独占影巢资源集成、风险管控、积分系统、自定义通知模板、智能合集、保号规则、邮件系统等功能。

### Q: 影巢 API Key 如何获取？

A: 登录 hdhive.com 后，进入个人设置 > API 管理创建。

### Q: 风控会影响正常用户吗？

A: 不会。风控仅检测异常行为，正常使用不受影响。VIP 用户可设置豁免。

### Q: 如何开启 Debug 日志？

A: 系统工具页面底部有 Debug 模式开关，开启后可查看详细请求日志。

### Q: 管理端口和用户端口为什么要分开？

A: 管理端口（10307）承载所有运维 API 与 Cookie 会话，对外暴露风险大；用户端口（10308）只挂载邀请注册、求片等公开页面，物理隔离后即使被扫描也无法触达管理面。

### Q: 反代后所有操作都报 `403 CSRF 验证失败：Origin 不匹配` 怎么办？

A: 反代未把浏览器看到的真实域名/协议传到容器内部。请在 Nginx / Caddy / Traefik
等反向代理上下发 `X-Forwarded-Proto`、`X-Forwarded-Host`（非默认端口再加
`X-Forwarded-Port`）。中间件位于 `app/core/csrf_middleware.py`，会用这三个头
组合出"合法源"用来对比 `Origin` / `Referer`，缺一不可。

## 🧪 本地开发

```bash
# 1. 安装依赖（推荐使用 uv）
pip install -r requirements.txt

# 2. 复制并填写环境变量
cp .env.example .env

# 3. 启动
python run.py
# 或：uvicorn app.main:app --host 0.0.0.0 --port 10307
```

**运行测试：**

```bash
uv run --with pytest pytest tests/ -v
```

> Windows 控制台输出含 Emoji，建议设置 `PYTHONIOENCODING=utf-8` 以避免 GBK 编码错误。

## ☕ 赞赏支持

如果您觉得 EmbyPulse-Pro 好用，欢迎赞赏支持作者的持续迭代！

<div align="center">
  <img src="static/img/zanshangma.png" alt="赞赏码" width="280" />
  <sub>（扫码赞赏，请备注您的 Telegram ID）</sub>
</div>

## 🙏 鸣谢

<div align="center">
  <a href="https://new.yunai.link/register?aff=rPv1">
    <img src="https://img.shields.io/badge/云AI-API%20平台-6366F1?style=for-the-badge&labelColor=4F46E5" alt="云AI" />
  </a>
  <br/>
  <sub>感谢 <a href="https://new.yunai.link/register?aff=rPv1">云AI</a> 对本项目的赞助支持</sub>
</div>

## 📄 许可证

本项目基于 MIT 许可证开源，附加条款：

- 二次开发必须保持开源
- 需保留原项目版权声明
- 禁止闭源封装或商业销售

<div align="center">
  <sub>EmbyPulse-Pro Team © 2024-2026</sub>
</div>
