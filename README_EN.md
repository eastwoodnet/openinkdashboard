# OpenInk (v1.4) · Universal E-Ink Dashboard & Server System

[English](README_EN.md) | [简体中文](README.md)

**OpenInk (v1.4)** is a self-hosted (BYOS) dashboard server and visual layout engine for Electronic Paper Displays (E-Ink). Built upon Python Cairo/Pango vector rendering, it supports flexible multi-page layout composition, 24h time-slot scheduling with nighttime DND sleep protection, HTTP long-polling incremental updates, dual-mode rotation, and instant big-text alert broadcasting via API.

---

## 🌟 Core Features

1. **Time-Slot Scheduling & Nighttime Screen Lifespan Protection (DND)**
   - Define custom time-slot rules throughout the day (e.g. morning focus, daytime work, evening, night sleep). Each slot can specify active pages and rotation intervals, with cross-midnight support.
   - During sleep hours, the physical screen remains stationary. Dates and calendar data update silently in the background at midnight (00:00), followed by a single clean refresh upon waking to minimize microcapsule wear and power usage.
   - During active hours, background scheduler polls data sources periodically and only triggers hardware refreshes when rendered content hashes change.

2. **Web Studio Management Interface**
   - **800×600 Real-Time Canvas Preview**: 1:1 pixel rendering feedback with an instant toggle between standard dashboard and full-screen big-text alert preview.
   - **Layout & Slot Composition**: Built-in 5 golden grid templates (`2|1 left two, right one`, `1|2 left one, right two`, `2×2 four quadrants`, `1×2 dual columns`, `1×1 full screen`). Easily add pages and assign data sources to each slot.
   - **Interactive Management**: Online todo list check-off and management, schedule rule editor, live weather city selection, and Home Assistant entity discovery.

3. **Modular Data Sources & External Plugins**
   - **Built-in Sources**: Solar/Lunar calendar with Chinese Ganzhi and 24 Solar Terms (`calendar`), live weather with multi-day forecasts (`weather`), local todo management (`todo`), full-screen focus broadsheet (`focus`), and instant notification overlay (`alert`).
   - **External Calendar Plugin (`agenda`)**: Subscribes to remote `.ics` calendars (iCloud, Google, Feishu, Nextcloud, etc.), extracts upcoming events and countdowns, and links event dots on the monthly calendar.
   - **Home Assistant Environment Plugin (`sensors`)**: Configurable Base URL and Long-Lived Access Token, dynamic discovery of smart home temperature/humidity sensors, customizable value mapping, and offline preview fallbacks.

4. **Universal Pull Protocol & Web Kiosk**
   - Standard HTTP endpoints distribute playlist manifests and 16-level grayscale PNGs. Supports `asyncio.Event`-based HTTP long-polling (`/api/v1/wait`) for millisecond-level reaction to layout changes and urgent alerts.
   - Built-in Web Kiosk terminal (`/kiosk`) for tablets, PCs, or browsers with fullscreen display and keyboard navigation.

---

## 🚀 Deployment Guide

### 1. Prerequisites & Dependencies

OpenInk requires Python 3.10+ and system `cairo` and `pango` graphics libraries:

```bash
# Install Debian / Ubuntu / Armbian system libraries
sudo apt update && sudo apt install -y python3-venv libcairo2 libpango-1.0-0 libpangocairo-1.0-0 gir1.2-pango-1.0 python3-gi-cairo fonts-wqy-microhei

# Create virtual environment (using --system-site-packages inherits system Cairo/GI bindings)
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start Service

```bash
# Local test run (listens on 127.0.0.1:8080 by default)
.venv/bin/python3 web_studio.py

# LAN / Production run (configure API Token and bind to all interfaces)
OPENINK_API_TOKEN='your-secure-token' OPENINK_BIND=0.0.0.0 OPENINK_PORT=8080 .venv/bin/python3 web_studio.py
```

- **Web Studio Management Dashboard**: `http://<SERVER_IP>:8080`
- **Web Kiosk Fullscreen Terminal**: `http://<SERVER_IP>:8080/kiosk`

### 3. Systemd Service Setup (Recommended)

Create `/etc/systemd/system/openink.service`:

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

## ⚙️ Configuration Guide

OpenInk enforces strict **separation of code, template defaults, and runtime credentials**:
- Sensitive credentials (e.g. API Token, HA Token) are loaded from environment variables or `.env`;
- Application configuration is stored in `config.json` (ignored by `.gitignore`, initialized from `config.example.json`).

### 1. Environment Variables (`.env`)

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
chmod 600 .env
```

Key environment variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `OPENINK_BIND` | `127.0.0.1` | Binding address. Use `0.0.0.0` for LAN deployments. |
| `OPENINK_PORT` | `8080` | Service listening port. Customizable to avoid conflicts. |
| `OPENINK_API_TOKEN` | Empty | Global API and management token. Recommended for non-loopback bindings. |
| `OPENINK_STUDIO_TRUSTED_CIDRS` | Empty | Trusted LAN CIDRs (e.g. `192.168.1.0/24`) allowed to access Studio without a Token. |
| `OPENINK_N516_NO_AUTH_IPS` | Empty | Device IPs exempted from token authentication (e.g. `192.168.111.1`). Applies only to `/api/v1/*`. |
| `OPENINK_ALLOW_INSECURE_NO_AUTH` | `0` | Set to `1` to confirm running without token on a trusted private network. |
| `HA_TOKEN` | Empty | Home Assistant Long-Lived Access Token (saved automatically when updated in Studio). |
| `HA_CA_FILE` | Empty | Path to private CA certificate for self-signed Home Assistant instances. |

### 2. Core Dashboard Configuration (`config.json`)

On startup, OpenInk loads `config.json` (or falls back to `config.example.json`). Main configuration schema:

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
        "title": "Page 1 · Main",
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
        { "title": "Milestone", "date": "+3", "time": "10:00", "is_countdown": true }
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
      { "id": "sensor.living_room_temp", "name": "Living Room Temp" }
    ]
  },
  "schedule": {
    "enabled": true,
    "active_interval_sec": 1800,
    "rules": [
      {
        "id": "day_work",
        "name": "Daytime Work",
        "start": "08:00",
        "end": "23:00",
        "mode": "carousel",
        "pages": ["page_1"],
        "carousel_interval_sec": 60
      },
      {
        "id": "night_dnd",
        "name": "Night Sleep DND",
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

## 🧩 Plugin Architecture & Custom Plugin Development

OpenInk uses a **startup-time discovery** and **on-demand collection** plugin architecture:
- **Zero background thread overhead**: Plugins are scanned and registered once when the service starts up;
- **On-demand execution**: The `collect()` function is only invoked when `plugins.<plugin_id>.enabled == true` in `config.json`. Disabled plugins make zero network requests;
- **Decoupled rendering**: Plugins can provide their own Cairo vector Widget. Once registered, the widget automatically appears in the Web Studio slot dropdown menu.

### 1. Plugin Directory Structure

Create a new directory in `src/plugins/` (for example, `src/plugins/stock_quote/`):

```text
src/plugins/stock_quote/
├── manifest.json       # Metadata & supported slot declarations
└── plugin.py           # Data collector & Cairo Widget renderer
```

### 2. Plugin Metadata Specification (`manifest.json`)

Declare plugin ID, UI labels, and which layout slot types it supports:
- `quadrant`: Quarter card (~368×264 pixels)
- `half_v`: Half-width vertical column (~368×537 pixels)
- `full`: Fullscreen 744×537 canvas

```json
{
  "id": "stock_quote",
  "name": "📈 Stocks & Equities",
  "short_name": "Stocks",
  "description": "Periodically fetches stock quotes and displays trends on E-Ink cards",
  "tier": "EXT",
  "slot_options": {
    "quadrant": {
      "id": "stock_quote",
      "name": "📈 Stocks (Plugin)",
      "desc": "Displays top 3 watched stocks with price and daily change"
    },
    "half_v": {
      "id": "stock_quote",
      "name": "📈 Stock Watchlist (Plugin)",
      "desc": "Full-height vertical card displaying full watchlist"
    }
  }
}
```

### 3. Implementing Collector & Cairo Widget (`plugin.py`)

Define the `collect` function and a widget class inheriting from `WidgetBase`:

```python
from typing import Dict, Any
import cairo
from profiles import DeviceProfile
from widgets.base import (
    WidgetBase, draw_pango_text, draw_dotted_kv_row,
    INK_BLACK, CARD_PAD_X, CARD_PAD_Y
)

def collect(cfg: Dict[str, Any], force_refresh: bool = False) -> Dict[str, Any]:
    """
    Data collector: invoked periodically only when plugins.stock_quote.enabled is true.
    Return value is mounted under global context['stock_quote'].
    """
    plugin_cfg = cfg.get("plugins", {}).get("stock_quote", {})
    # Example: fetch external API
    return {
        "items": [
            {"symbol": "AAPL", "price": "180.5", "change": "+1.2%"},
            {"symbol": "MSFT", "price": "420.0", "change": "-0.5%"}
        ]
    }

class StockWidget(WidgetBase):
    id = "stock_quote"
    name = "Stock Watchlist"
    description = "Stock market quotes widget"

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
        Renders crisp 16-level grayscale content with Cairo.
        :param cr: Cairo Context
        :param w, h: Pixel dimensions of the current slot (e.g. 368x264)
        :param slot_type: 'quadrant' | 'half_v' | 'full'
        :param context: Global context dictionary
        :param profile: Hardware device profile
        """
        data = context.get("stock_quote", {})
        stocks = data.get("items", [])

        draw_pango_text(cr, "■ Stock Quotes", CARD_PAD_X, CARD_PAD_Y, 17, bold=True, color=INK_BLACK)
        
        start_y = CARD_PAD_Y + 45
        for idx, item in enumerate(stocks[:3]):
            cur_y = start_y + idx * 40
            draw_dotted_kv_row(
                cr, item["symbol"], f"{item['price']} ({item['change']})",
                CARD_PAD_X, cur_y, w - CARD_PAD_X * 2,
                row_h=30, label_size=15, val_size=16
            )

# Export for plugin discovery
WIDGET_CLASS = StockWidget
```

> **Plugin Security Best Practices**:
> 1. **URL Validation**: Use `from config import validate_external_url` to prevent SSRF vulnerabilities when querying remote services;
> 2. **Secret Isolation**: Never store API tokens in plaintext inside `config.json`. Use environment variables and load them via `from config import get_secret`;
> 3. **Service Reload**: After creating or updating a plugin, restart the service with `sudo systemctl restart openink`.

---

## 🔒 API Authentication & External Application Integration

When `OPENINK_API_TOKEN` is configured, requests to administrative endpoints, data mutations, and alert broadcasts are authenticated.

### 1. Authentication Methods

External applications can pass credentials through:
1. **HTTP Headers (Recommended)**:
   - `X-API-Token: <your-token>`
   - `Authorization: Bearer <your-token>`
2. **URL Query Parameter (For constrained environments or simple webhooks)**:
   - `?token=<your-token>`

> **Security Details**:
> - External notification endpoints (`/api/alert/*`) strictly require token authentication.
> - Image asset URLs served to clients **do not embed plaintext tokens**, preventing credential leakage during asset fetching.
> - If `OPENINK_STUDIO_TRUSTED_CIDRS` is set, browser requests to Web Studio from matching IPs bypass manual token entry while remaining protected against cross-site requests.

### 2. Instant Big-Text Alert API

External systems (such as Home Assistant automations, iOS Shortcuts, monitoring webhooks, or shell scripts) can broadcast high-priority notifications to OpenInk. The server immediately renders a 16-level grayscale alert card and wakes up connected clients:

#### Standard JSON Push (`POST /api/alert/push`)

```bash
curl -X POST http://<SERVER_IP>:8080/api/alert/push \
  -H "Content-Type: application/json" \
  -H "X-API-Token: your-secure-token" \
  -d '{
    "title": "Server Alert",
    "text": "Daily database backup completed successfully.",
    "sender": "OpsMonitor",
    "duration": 15
  }'
```

- `title` *(string)*: Alert title banner.
- `text` *(string, required)*: Notification message body with automatic line wrapping.
- `sender` *(string, optional)*: Origin identifier, defaults to `"OpenInk"`.
- `duration` *(int, optional)*: Display duration in minutes (defaults to 15). Returns to dashboard carousel when expired.

#### Quick GET Request (`GET /api/alert/quick`)

Ideal for browser bookmarks, iOS Shortcuts, or simple webhook triggers:

```bash
curl -G "http://<SERVER_IP>:8080/api/alert/quick" \
  --data-urlencode "title=Doorbell" \
  --data-urlencode "text=Motion detected at the front door" \
  --data-urlencode "sender=Security" \
  --data-urlencode "duration=10" \
  --data-urlencode "token=your-secure-token"
```

#### Dismiss Alert (`POST /api/alert/dismiss`)

```bash
curl -X POST http://<SERVER_IP>:8080/api/alert/dismiss \
  -H "X-API-Token: your-secure-token"
```

Physical keystrokes (`Enter`, `Return`, or `Space`) on the Hanvon N516 or Web Kiosk also immediately dismiss the notification.

### 3. Online Todos API (`/api/todos/*`)

- `GET /api/todos`: Fetches the current todo list and completion counts.
- `POST /api/todos/add`: Adds a new item (`{"text": "Replace air filter"}`).
- `POST /api/todos/toggle`: Toggles item completion status (`{"id": 1}`).
- `POST /api/todos/delete`: Deletes a specified item.
- `POST /api/todos/clear`: Clears all completed items.

---

## 📱 Device Integration & Hardware Compatibility

### 1. Hanvon N516 (OpenInkpot · USB Network)

For Hanvon N516 devices connected via point-to-point USB networking, a dedicated persistent client daemon is provided:

```bash
# Execute deployment script on the host (writes to N516 NAND Flash via SSH)
./clients/n516-openinkpot/install_n516.sh n516
```

- **BusyBox `init` Native Supervision**: Managed via `/etc/inittab` (`::respawn:/usr/local/bin/openink-agent.sh`) for automatic restarts after exits or system reboots.
- **150ms In-Place Refresh**: Employs double buffering and `NEXT_IMAGE` key injection to bypass madeye's image cache without window restarts.
- **Zero-CPU Offline Smart Sleep**: Enters sleep mode when the USB carrier drops and auto-recovers synchronization immediately when reconnected.

### 2. Amazon Kindle & Generic Wi-Fi E-Ink Devices

OpenInk uses a universal pull protocol compatible with any device capable of fetching HTTP assets and displaying images (e.g. jailbroken Kindles, Android e-readers, ESP32 boards, TRMNL):

```bash
# 1. Fetch current display manifest and image URL
JSON=$(curl -s "http://<SERVER_IP>:8080/api/v1/display?device_id=kindle")
IMG_URL=$(echo "$JSON" | grep -o 'http[^"]*landscape[^"]*' | head -n 1)

# 2. Download and render to e-ink screen
curl -s "$IMG_URL" -o /tmp/screen.png
# Display using the device tool (e.g. eips on Kindle)
eips -g /tmp/screen.png
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
