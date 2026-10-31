# OpenInk · 通用墨水屏看板与插件编排系统

[English](README_EN.md) | [简体中文](README.md)

**OpenInk (v1.3)** 是一套面向电子墨水屏（E-Ink）终端的高性能自建看板服务（BYOS）与可视化排版系统。基于 **Python Cairo/Pango 几何矢量渲染引擎** 与 **模块化外部插件架构**，提供全时段排程休眠、多页版式自由编排、秒级通用 HTTP 长轮询增量同步、双模自动轮播与终端交互响应。

---

## 🌟 核心特性 (v1.3)

1. **24 小时全时段分页面排程与休眠免打扰 (`src/scheduler.py`)**
   - **全天分时段自定义**：支持按时间段（如早晨焦点、日间工作、傍晚生活、夜间休眠）独立指定生效页面与轮播节奏，支持跨午夜时间段定义。
   - **墨水屏寿命保护型休眠 (DND)**：休眠期间屏幕保持静止不翻页，后台在 00:00 静默更新日历与数据；早晨唤醒时一次性刷新推送到屏幕，最大化减少墨水屏微胶囊磨损与电力损耗。
   - **时段保鲜调度**：非休眠时段定时检查数据更新，内容有变化时才下发硬件刷新，杜绝无意义的频闪。

2. **现代化左右分栏 Web Studio 工作台 (`templates/studio.html`)**
   - **左侧 800×600 实时置顶预览**：等比像素级画布反馈，右上角可一键在「常规看板预览」与「大字通知效果预览」间无缝切换。
   - **右侧 4 大功能分类选项卡**（告别长瀑布流）：
     - `📑 页面编排`：多页管理、轮播/手动翻页、5 种黄金分栏结构、卡片槽位数据源绑定与插件开关。
     - `⏰ 时段排程`：排程总开关、当前排期执行倒计时、保鲜周期、时段规则可视化增删改。
     - `🔌 数据源`：外部日历 (ICS) 与倒数日、实时天气、待办清单、Home Assistant 环境传感器、农历日历。
     - `⚙️ 设备通知`：全屏即时大字通知推送与预览、180° 一键翻转、Web Kiosk、API Token。

3. **核心数据源与外部插件解耦架构 (`src/plugins/`)**
   - **内置核心数据源**：公历/农历干支节气日历 (`calendar`)、实时天气与未来趋势 (`weather`)、待办清单管理 (`todo`)、综合焦点画报 (`focus`)、即时大字通知 (`alert`)。
   - **外部数据源插件**：根据 `config.json` 中 `plugins.<id>.enabled` 动态按需加载：
     - **0 级插件 (`agenda`)**：订阅 iCloud / Google / 飞书等 `.ics` 外部日历，支持日程重要度高亮、纪念日/倒数日计算，并自动联动月历打点。
     - **环境插件 (`sensors`)**：接入 Home Assistant 室内温湿度与环境指标。

4. **多页动态编排与版式复用 (`LayoutComposer`)**
   - 内置 5 套黄金网格分栏：`2|1 左二右一`、`1|2 左一右二`、`2×2 四象限`、`1×2 左右双栏`、`1×1 全屏单卡`。
   - 支持自由扩展第 1 页、第 2 页、第 3 页……每页均可独立选择网格分栏与数据源插槽。
   - 支持 **自动轮播 (`carousel`)** 与 **手动翻页 (`manual`)**，轮播间隔涵盖 30秒 至 24小时。

5. **通用拉取协议与长轮询实时同步 (`/api/v1/*` + `/kiosk`)**
   - `GET /api/v1/display`：返回当前播放列表清单、各页 MD5 短哈希、轮播模式、排程时段与紧急通知状态。
   - `GET /api/v1/wait`：基于 `asyncio.Event` 的 HTTP 长轮询挂起接口，毫秒级响应配置变更与即时通知。
   - `GET /api/v1/assets/{bucket}/{filename}`：分发适合竖屏硬件 (`portrait`, 600×800) 与横屏/网页 (`landscape`, 800×600) 的 16 级灰阶图像。
   - `GET/POST /api/v1/event`：终端物理按键/触控回调（勾选待办、清理完成项、解除通知或刷新数据）。
   - `GET /kiosk`：零安装全屏 Web Kiosk 终端，支持键盘翻页、全屏模式与待办快捷勾选。

6. **灵活端口配置与多服务并存 (`OPENINK_PORT`)**
   - 原生支持通过环境变量 `OPENINK_PORT` 指定运行端口（默认推荐 `8080`），可与主机上已运行的其他 8000 端口服务（如 `esp32-gateway`、其他 Web 中继）在同一台 Linux/Armbian 主机上零冲突共存。

---

## 🚀 部署指南

### 1. 环境准备与依赖安装

系统要求：Linux / macOS，Python 3.10+，并具备 `cairo`、`pango` 底层图形库。

```bash
# Debian / Ubuntu / Armbian 环境依赖
sudo apt update && sudo apt install -y python3-venv libcairo2 libpango-1.0-0 libpangocairo-1.0-0 gir1.2-pango-1.0 python3-gi-cairo fonts-wqy-microhei

# 创建虚拟环境（推荐使用 --system-site-packages 继承系统 Cairo/GI 绑定）
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 启动服务端

```bash
# 本地测试启动（默认监听 0.0.0.0:8080）
OPENINK_BIND=0.0.0.0 OPENINK_PORT=8080 .venv/bin/python3 web_studio.py
```

- **OpenInk Studio 管理面板**：`http://<主机IP>:8080`
- **Web Kiosk 全屏终端**：`http://<主机IP>:8080/kiosk`

### 3. 配置 Systemd 常驻服务 (生产环境推荐)

创建 `/etc/systemd/system/openink.service`：

```ini
[Unit]
Description=OpenInk E-Ink Display Server & Studio
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/openink
Environment=OPENINK_BIND=0.0.0.0
Environment=OPENINK_PORT=8080
Environment=OPENINK_API_TOKEN=
ExecStart=/opt/openink/venv/bin/python3 /opt/openink/web_studio.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now openink
sudo systemctl status openink
```

---

## 📱 终端接入与硬件适配说明

### 1. 汉王 N516 (OpenInkpot · USB Network) 终端一键部署
针对 N516 USB Network 终端，项目提供了 100% 重启持久化与断网休眠省电的守护进程：

```bash
# 在服务端执行一键部署脚本（通过 SSH 写入 N516 NAND Flash）
./clients/n516-openinkpot/install_n516.sh n516
```

- **持久化按键生成**：守护进程启动时自动在 `/tmp/openink_keys/` 动态构建 64 字节 Linux `struct input_event` 二进制流，彻底解决 `/tmp` 重启丢失按键的问题。
- **150ms 无闪原地刷新**：利用双缓冲机制与 `NEXT_IMAGE` 步进，绕过 madeye 内存文件缓存，无需重启窗口即可原地刷新。
- **智能休眠省电**：仅当 USB 处于联网状态 (`carrier=1`) 时保持拉取与轮播；断开 USB 时守护进程自动退出，设备进入原生硬件深度休眠，充当纯粹的电子书。

### 2. 亚马逊 Kindle 与通用 Wi-Fi 墨水屏终端说明

> [!NOTE]
> **Kindle 通用性说明**：本项目初期主要基于汉王 N516 进行实机联调，作者暂未直接使用 Kindle 机器进行深度验证。但从架构设计上，OpenInk 采用了**设备无关的通用 HTTP 拉取协议（Universal Pull Protocol）**。只要在已越狱的 Kindle 或其他 Wi-Fi 墨水屏（如 Android 电纸书、ESP32 墨水屏板、TRMNL）上维护一个极简的定时拉取脚本，并填入服务端的 IP 与端口，**大概率即可完全通用**！

**Kindle 端极简运行思路**：
1. **网络连接**：Kindle 自带 Wi-Fi 网卡，保持接入局域网。
2. **定时拉取脚本**：使用 Kindle 内置的 `curl` 或 `wget` 定时/休眠唤醒请求：
   ```sh
   # 1. 获取播放清单 JSON，提取图片 URL
   JSON=$(curl -s "http://<服务器IP>:8080/api/v1/display?device_id=kindle")
   IMG_URL=$(echo "$JSON" | grep -o 'http[^"]*landscape[^"]*' | head -n 1)

   # 2. 下载 16 级灰阶画面并刷屏展示
   curl -s "$IMG_URL" -o /tmp/screen.png
   eips -g /tmp/screen.png
   ```
3. **安全鉴权**：若服务部署在外网，只需在请求时追加 `?token=your-secret-token` 或请求头 `X-API-Token`。

---

## 🔒 外网反向代理与 API Token 鉴权

OpenInk 默认采用 **局域网免配置模式**（未设置 `OPENINK_API_TOKEN` 时免密访问，Web 面板自动隐藏密钥输入框）。

当您需要将服务部署在公网，或需要防护外部 Webhook 时，可通过环境变量设置 Token：

```bash
export OPENINK_API_TOKEN="your-secure-token"
```

支持三种传入方式，全面兼容各类设备环境：
1. **HTTP Header (标准 API)**：`X-API-Token: your-secure-token`
2. **Bearer Header (标准 Webhook)**：`Authorization: Bearer your-secure-token`
3. **URL Query (嵌入式终端 / 快捷指令)**：`?token=your-secure-token`
   - 当终端使用 `GET /api/v1/display?token=...` 请求时，服务端下发的图像 URL 会自动携带 `token` 凭据，方便轻量级固件直接下载。

---

## 📢 即时大字通知推送 (Instant Alert API)

OpenInk 支持**毫秒级插播即时大字通知**。当外部系统（如人在室外时手机触发、Home Assistant 自动化、企业微信/飞书 Webhook、监控告警脚本或 iOS 快捷指令）发送通知请求时，服务端会立即生成专用的 16 级灰阶大字画报（居中大字标题、自适应正文字号、来源徽标与有效倒计时），并通过 HTTP 长轮询挂起点毫秒级唤醒墨水屏终端打断轮播，立即呈现通知。

### 1. 标准 JSON 格式推送 (`POST /api/alert/push`)

```bash
curl -X POST http://<主机IP>:8080/api/alert/push \
  -H "Content-Type: application/json" \
  -H "X-API-Token: your-secure-token" \
  -d '{
    "title": "会议提醒",
    "text": "10分钟后在第3会议室召开敏捷评审会，请携带笔记本。",
    "sender": "企业微信",
    "duration": 15
  }'
```

**请求字段说明**：
- `title` *(string)*: 通知大标题（例如 `"桌面备忘"`、`"门铃提醒"`、`"运维告警"`）。
- `text` *(string, 必选)*: 通知正文内容，自动计算字号与优雅折行排版。
- `sender` *(string, 可选)*: 来源徽标，默认 `"OpenInk"`。
- `duration` *(int, 可选)*: 保持时长（分钟），默认 15 分钟。超时后设备自动恢复原看板轮播。

### 2. 单行快捷 GET 请求 (`GET /api/alert/quick`)

适合在**手机浏览器书签**、**iOS 快捷指令（捷径）**、**Tasker** 或 **Home Assistant `rest_command`** 中直接调用：

```bash
# 推荐使用 --data-urlencode（自动处理中文字符转义）
curl -G "http://<主机IP>:8080/api/alert/quick" \
  --data-urlencode "title=快递到达" \
  --data-urlencode "text=您的顺丰快递已投递至蜂巢快递柜" \
  --data-urlencode "sender=菜鸟驿站" \
  --data-urlencode "duration=20" \
  --data-urlencode "token=your-secure-token"
```

### 3. 手动解除即时通知 (`POST /api/alert/dismiss` 或 物理按键)

- **HTTP 接口解除**：
  ```bash
  curl -X POST http://<主机IP>:8080/api/alert/dismiss -H "X-API-Token: your-secure-token"
  # 或快捷 GET 请求:
  curl "http://<主机IP>:8080/api/alert/dismiss?token=your-secure-token"
  ```
- **终端物理交互解除**：在汉王 N516 或 Web Kiosk 终端上按下 `Enter` / `Return` / `空格键`，即可立即关闭当前通知并恢复主看板轮播。

---

## 🗺️ 后续版本路线图

- **v1.2 (当前版本)**：
  - 架构全面解耦，去特定设备硬编码；
  - 通用拉取协议与 HTTP 长轮询秒级响应；
  - 端口环境变量解耦 (`OPENINK_PORT`)，支持与现有 8000 端口服务无缝并存；
  - 自动轮播时间扩展至小时级（支持心跳式分段长轮询）；
  - Web Kiosk 零安装全屏终端。
- **v1.3 (规划中 · 数码相框与照片轮播)**：
  - **E-Ink 灰度相册管线**：支持 JPEG/PNG 图片上传，自动构图居中裁剪与 16 级灰阶量化；
  - **抖动算法引擎**：集成 Floyd-Steinberg / Atkinson 误差扩散抖动，呈现高细节相片质感；
  - **混排与独立相框**：支持「主看板 + 家庭相册」混合轮播，或独立全屏数码相框模式。
