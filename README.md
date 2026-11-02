# OpenInk (v1.4) · 通用墨水屏看板与服务端系统

[English](README_EN.md) | [简体中文](README.md)

**OpenInk (v1.4)** 是面向电子墨水屏（E-Ink）终端的自建看板服务（BYOS）与排版系统。采用 Python Cairo/Pango 矢量渲染，支持多页版式自由编排、分时段排程与夜间休眠（DND）、HTTP 长轮询增量同步、双模自动轮播，以及通过 API 接收外部系统的即时大字通知。

---

## 🌟 核心功能

1. **分时段排程与夜间休眠保护 (DND)**
   - 支持全天分时段规则（如晨间、日间工作、晚间、夜间休眠），每时段可独立指定展示页面与轮播间隔，支持跨午夜时间段。
   - 夜间休眠时段屏幕保持静止，零点后台静默更新日历与数据；早晨唤醒时一次性刷新，减少墨水屏微胶囊磨损与功耗。
   - 非休眠时段定时检查数据更新，仅当渲染哈希发生变化时才触发终端刷新，避免无效闪烁。

2. **Web Studio 可视化管理面板**
   - **800×600 实时画布预览**：等比像素级渲染反馈，支持在常规看板与大字通知效果之间一键切换预览。
   - **分栏与槽位编排**：内置 5 种版式（`2|1 左二右一`、`1|2 左一右二`、`2×2 四象限`、`1×2 左右双栏`、`1×1 全屏单卡`），支持自由扩展页面并为每个槽位选择数据源。
   - **在线管理配置**：集成待办事项在线勾选与编辑、时段排程规则配置、天气城市切换、Home Assistant 实体在线检索。

3. **模块化数据源与插件支持**
   - **内置数据源**：公历/农历干支节气日历 (`calendar`)、实时天气与未来趋势 (`weather`)、本地待办清单 (`todo`)、综合焦点画报 (`focus`)、即时大字通知 (`alert`)。
   - **外部日历插件 (`agenda`)**：订阅 iCloud、Google、飞书等 `.ics` 远程日历，自动解析日程与倒数日，并在月历视图中联动打点。
   - **Home Assistant 环境监控插件 (`sensors`)**：支持配置实例地址与长期访问令牌，自动检索温湿度等传感器实体，提供数值映射与离线回退。

4. **通用拉取协议与 Web Kiosk**
   - 基于标准 HTTP 接口下发展示清单与 16 级灰阶图像，支持基于 `asyncio.Event` 的 HTTP 长轮询（`/api/v1/wait`），页面变更或新通知毫秒级下发。
   - 内置 Web Kiosk 终端（`/kiosk`），可在平板、电脑或移动设备浏览器中全屏运行并支持快捷键翻页与交互。

---

## 🚀 部署指南

### 1. 系统依赖与虚拟环境

OpenInk 需要 Python 3.10+ 以及系统底层的 `cairo` 和 `pango` 图形库：

```bash
# Debian / Ubuntu / Armbian 安装底层依赖
sudo apt update && sudo apt install -y python3-venv libcairo2 libpango-1.0-0 libpangocairo-1.0-0 gir1.2-pango-1.0 python3-gi-cairo fonts-wqy-microhei

# 创建虚拟环境（推荐使用 --system-site-packages 继承系统 Cairo/GI 绑定）
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 启动服务

```bash
# 本地测试启动（默认仅监听 127.0.0.1:8080）
.venv/bin/python3 web_studio.py

# 局域网/生产环境启动（设置 API Token 并监听全部网卡）
OPENINK_API_TOKEN='your-secure-token' OPENINK_BIND=0.0.0.0 OPENINK_PORT=8080 .venv/bin/python3 web_studio.py
```

- **Web Studio 管理面板**：`http://<主机IP>:8080`
- **Web Kiosk 全屏终端**：`http://<主机IP>:8080/kiosk`

### 3. Systemd 常驻服务配置 (推荐)

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
Environment=OPENINK_API_TOKEN=your-secure-token
ExecStart=/opt/openink/.venv/bin/python3 /opt/openink/web_studio.py
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

## ⚙️ 配置文件说明

OpenInk 严格执行**代码、配置模板与敏感凭据分离**的原则：
- 敏感凭据（如 API Token、HA 密钥）通过环境变量或本地 `.env` 文件读取；
- 业务配置保存在 `config.json`（已被 `.gitignore` 忽略，仓库仅提供 `config.example.json` 作为模板）。

### 1. 环境变量配置 (`.env`)

复制模板文件 `.env.example` 为 `.env`：

```bash
cp .env.example .env
chmod 600 .env
```

核心配置项说明：

| 环境变量名 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `OPENINK_BIND` | `127.0.0.1` | 监听地址。局域网部署可设为 `0.0.0.0`。 |
| `OPENINK_PORT` | `8080` | 服务运行端口。可自定义以避免与其他服务冲突。 |
| `OPENINK_API_TOKEN` | 空 | 全局访问与管理密钥。非回环监听时推荐配置。 |
| `OPENINK_STUDIO_TRUSTED_CIDRS` | 空 | 可信局域网网段（如 `192.168.1.0/24`）。该网段内访问 Studio 面板可免验 Token。 |
| `OPENINK_N516_NO_AUTH_IPS` | 空 | 豁免 Token 的设备 IP（如 USB 点对点地址 `192.168.111.1`）。仅对 `/api/v1/*` 终端接口生效。 |
| `OPENINK_ALLOW_INSECURE_NO_AUTH` | `0` | 在未配置 Token 且监听非回环地址时，置 `1` 显式确认运行在受信任私网中。 |
| `HA_TOKEN` | 空 | Home Assistant 长期访问令牌（系统通过 Web Studio 保存时会自动存入此文件）。 |
| `HA_CA_FILE` | 空 | 自签名 Home Assistant 实例的私有 CA 证书路径。 |

### 2. 看板核心配置 (`config.json`)

系统启动时会自动读取 `config.json`，若文件不存在则以 `config.example.json` 作为初始默认值。各主要配置块结构如下：

```json
{
  "city": "Beijing",
  "dashboard": {
    "mode": "carousel",
    "carousel_interval_sec": 60,
    "template": "2_1",
    "pages": [
      {
        "id": "page_1",
        "title": "第 1 页 · 主看板",
        "template": "2_1",
        "slots": {
          "top_left": "calendar",
          "bottom_left": "weather",
          "right": "todo"
        }
      }
    ]
  },
  "plugins": {
    "agenda": {
      "enabled": true,
      "ics_urls": ["https://example.com/calendar.ics"],
      "items": [
        { "title": "项目里程碑", "date": "+3", "time": "10:00", "is_countdown": true }
      ]
    },
    "sensors": {
      "enabled": true
    }
  },
  "homeassistant": {
    "url": "http://192.168.1.100:8123",
    "token_env": "HA_TOKEN",
    "sensors": [
      { "id": "sensor.living_room_temp", "name": "客厅温度" }
    ]
  },
  "schedule": {
    "enabled": true,
    "active_interval_sec": 1800,
    "rules": [
      {
        "id": "day_work",
        "name": "日间工作",
        "start": "08:00",
        "end": "23:00",
        "mode": "carousel",
        "pages": ["page_1"],
        "carousel_interval_sec": 60
      },
      {
        "id": "night_dnd",
        "name": "夜间休眠",
        "start": "23:00",
        "end": "08:00",
        "mode": "sleep_dnd",
        "pages": [],
        "allow_alert_override": true
      }
    ]
  }
}
```

---

## 🧩 插件机制与自定义插件编写规范

OpenInk 采用**启动时自动发现（Startup-Time Discovery）**与**按需采集（On-Demand Collection）**的插件化架构：
- **零后台巡检常驻开销**：插件在服务启动时自动扫描注册，无需后台常驻线程；
- **开关隔离**：仅当 `config.json` 中 `plugins.<plugin_id>.enabled == true` 时，系统才会在刷新时执行数据采集，未启用时完全不发起网络请求；
- **渲染解耦**：插件可自带 Cairo 矢量渲染卡片（Widget），注册后自动出现在 Web Studio 相应槽位的下拉选择列表中。

### 1. 插件目录结构

在 `src/plugins/` 目录下创建新插件文件夹（例如 `src/plugins/stock_quote/`），包含两个文件：

```text
src/plugins/stock_quote/
├── manifest.json       # 插件元数据与支持的卡片槽位声明
└── plugin.py           # 数据采集器与 Cairo Widget 渲染类
```

### 2. 插件元数据规范 (`manifest.json`)

声明插件唯一 ID、界面显示名称，以及该插件适用的卡片槽位类型：
- `quadrant`: 四象限小卡片（约 368×264 像素）
- `half_v`: 纵向全高半宽卡片（约 368×537 像素）
- `full`: 744×537 全屏单卡

```json
{
  "id": "stock_quote",
  "name": "📈 自选股票与行情",
  "short_name": "自选股",
  "description": "定时拉取自选股票行情并在墨水屏卡片中展示",
  "tier": "EXT",
  "slot_options": {
    "quadrant": {
      "id": "stock_quote",
      "name": "📈 自选股卡片 (Plugin)",
      "desc": "展示前 3 项重点自选股票现价与涨跌幅"
    },
    "half_v": {
      "id": "stock_quote",
      "name": "📈 自选股全高列表 (Plugin)",
      "desc": "全高纵向展示自选股票列表与走势"
    }
  }
}
```

### 3. 数据采集与渲染实现 (`plugin.py`)

`plugin.py` 中需定义 `collect` 函数以及继承 `WidgetBase` 的渲染类：

```python
from typing import Dict, Any
import cairo
from profiles import DeviceProfile
from widgets.base import (
    WidgetBase, draw_pango_text, draw_pango_text_right,
    draw_rounded_rect, draw_dotted_kv_row, INK_BLACK, INK_DIVIDER,
    CARD_PAD_X, CARD_PAD_Y
)
from config import validate_external_url, get_secret

def collect(cfg: Dict[str, Any], force_refresh: bool = False) -> Dict[str, Any]:
    """
    数据采集器：当且仅当 plugins.stock_quote.enabled 为 true 时被定时调用。
    返回值会自动挂载至全局 context['stock_quote'] 中。
    """
    plugin_cfg = cfg.get("plugins", {}).get("stock_quote", {})
    # 示例：通过安全网络校验函数请求外部 API 或本地服务
    return {
        "items": [
            {"symbol": "AAPL", "price": "180.5", "change": "+1.2%"},
            {"symbol": "MSFT", "price": "420.0", "change": "-0.5%"}
        ]
    }

class StockWidget(WidgetBase):
    id = "stock_quote"
    name = "自选股票看板"
    description = "自选股票行情卡片"

    def render(
        self,
        cr: cairo.Context,
        w: int,
        h: int,
        slot_type: str,
        context: Dict[str, Any],
        profile: DeviceProfile
    ):
        """
        基于 Cairo 矢量绘图上下文渲染内容（保证 16 级灰阶墨水屏清晰高对比度）。
        :param cr: Cairo Context
        :param w, h: 当前槽位的像素宽高 (如 368x264)
        :param slot_type: 'quadrant' | 'half_v' | 'full'
        :param context: 包含内置数据与所有已启用插件数据的全局上下文字典
        :param profile: 硬件设备配置（包含颜色支持、长宽等）
        """
        data = context.get("stock_quote", {})
        stocks = data.get("items", [])

        # 标题栏绘制
        draw_pango_text(cr, "■ 自选股行情", CARD_PAD_X, CARD_PAD_Y, 17, bold=True, color=INK_BLACK)
        
        # 虚线键值对行
        start_y = CARD_PAD_Y + 45
        for idx, item in enumerate(stocks[:3]):
            cur_y = start_y + idx * 40
            draw_dotted_kv_row(
                cr, item["symbol"], f"{item['price']} ({item['change']})",
                CARD_PAD_X, cur_y, w - CARD_PAD_X * 2,
                row_h=30, label_size=15, val_size=16
            )

# 导出供插件系统识别
WIDGET_CLASS = StockWidget
```

> **插件开发安全最佳实践**：
> 1. **URL 安全白名单**：发起外部 HTTP 请求前，建议调用 `from config import validate_external_url` 或 `resolve_external_url`，防止针对内网私网地址的 SSRF 漏洞；
> 2. **凭据安全隔离**：插件如需调用带 Token 的第三方服务，严禁在 `config.json` 中存盘明文密码，应通过 `from config import get_secret` 从环境变量或 `.env` 注入；
> 3. **重启生效**：新增或修改插件代码后，执行 `sudo systemctl restart openink` 重载服务即可。

---

## 🔒 API 鉴权与外部应用通信机制

当服务端配置了 `OPENINK_API_TOKEN` 时，所有针对管理接口、数据更新以及即时通知的请求均会触发鉴权。

### 1. 通信鉴权方式

外部应用可通过以下任一方式传递凭据：
1. **HTTP 请求头 (推荐)**：
   - `X-API-Token: <your-token>`
   - `Authorization: Bearer <your-token>`
2. **URL Query 参数 (适用于受限环境或简易 Webhook)**：
   - `?token=<your-token>`

> **安全机制**：
> - 外部通知接口（`/api/alert/*`）始终强制校验 Token。
> - 服务端在向终端下发的图像资产 URL 中**不会拼接明文 Token**，防止图像下载请求泄露认证凭据。
> - 若配置了 `OPENINK_STUDIO_TRUSTED_CIDRS`，仅限该网段的局域网浏览器访问 Web Studio 时豁免输入 Token，并受到来源检查（Same-Origin）防护。

### 2. 即时大字通知推送 (Instant Alert API)

外部应用（如 Home Assistant 自动化、iOS 快捷指令、监控报警脚本、企业微信 Webhook 等）可向 OpenInk 发送即时插播通知。服务端会立即生成 16 级灰阶大字画报并毫秒级唤醒终端呈现。

#### 标准 JSON 推送 (`POST /api/alert/push`)

```bash
curl -X POST http://<主机IP>:8080/api/alert/push \
  -H "Content-Type: application/json" \
  -H "X-API-Token: your-secure-token" \
  -d '{
    "title": "运维告警",
    "text": "核心备份任务完成，存储池健康度正常。",
    "sender": "监控中心",
    "duration": 15
  }'
```

- `title` *(string)*: 通知大标题。
- `text` *(string, 必选)*: 通知正文内容，自动计算字号与优雅折行。
- `sender` *(string, 可选)*: 发送方标识，默认 `"OpenInk"`。
- `duration` *(int, 可选)*: 展示时长（分钟），默认 15 分钟。超时后自动恢复原看板轮播。

#### 快捷 GET 请求 (`GET /api/alert/quick`)

适合在浏览器书签、iOS 捷径或轻量 Webhook 中调用：

```bash
curl -G "http://<主机IP>:8080/api/alert/quick" \
  --data-urlencode "title=门铃提醒" \
  --data-urlencode "text=门口检测到访客按门铃" \
  --data-urlencode "sender=门禁系统" \
  --data-urlencode "duration=10" \
  --data-urlencode "token=your-secure-token"
```

#### 解除通知 (`POST /api/alert/dismiss`)

```bash
curl -X POST http://<主机IP>:8080/api/alert/dismiss \
  -H "X-API-Token: your-secure-token"
```

在汉王 N516 或 Web Kiosk 终端上按下 `Enter` / `Return` / `空格键` 也可直接物理关闭当前通知。

### 3. 在线待办事项 API (`/api/todos/*`)

- `GET /api/todos`：获取当前待办列表与统计数据。
- `POST /api/todos/add`：添加待办（`{"text": "购买滤芯"}`）。
- `POST /api/todos/toggle`：切换指定待办的完成状态（`{"id": 1}`）。
- `POST /api/todos/delete`：删除指定序号待办。
- `POST /api/todos/clear`：一键清除所有已完成待办。

---

## 📱 终端设备接入与硬件适配

### 1. 汉王 N516 (OpenInkpot · USB Network) 终端

针对 N516 通过 USB 与网关/服务器连接的点对点场景，项目提供了专用持久化守护脚本：

```bash
# 在服务端执行一键部署脚本（通过 SSH 写入 N516 NAND Flash）
./clients/n516-openinkpot/install_n516.sh n516
```

- **BusyBox `init` 原生常驻**：注册为 `/etc/inittab` 重生进程（`::respawn:/usr/local/bin/openink-agent.sh`），异常退出或冷重启后自动拉起。
- **150ms 无闪原地刷新**：利用双缓冲机制与 `NEXT_IMAGE` 按键注入绕过 madeye 缓存，避免重启窗口。
- **断网 0% CPU 智能休眠**：检测到 USB 网卡断开时进入休眠等待，重新接通后自动自愈恢复同步。

### 2. 亚马逊 Kindle 与通用 Wi-Fi 墨水屏设备

OpenInk 采用通用的 HTTP 拉取协议，支持任何具备网络连接与图像显示能力的墨水屏终端（如已越狱 Kindle、Android 电纸书、ESP32 墨水屏、TRMNL 等）。

**通用拉取流程示例**：
```bash
# 1. 查询当前播放清单与图像 URL
JSON=$(curl -s "http://<主机IP>:8080/api/v1/display?device_id=kindle")
IMG_URL=$(echo "$JSON" | grep -o 'http[^"]*landscape[^"]*' | head -n 1)

# 2. 下载并呈现到屏幕
curl -s "$IMG_URL" -o /tmp/screen.png
# 使用终端专属工具刷新屏幕（例如 Kindle 的 eips 命令）
eips -g /tmp/screen.png
```

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源。
