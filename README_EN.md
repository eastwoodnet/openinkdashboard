# OpenInk · Universal E-Ink Dashboard & Plugin Studio

[English](README_EN.md) | [简体中文](README.md)

**OpenInk (v1.2)** is a high-performance, self-hosted (BYOS) dashboard service and visual layout engine for Electronic Paper Displays (E-Ink). Built upon a **Python Cairo/Pango geometric vector rendering pipeline** and a **modular external data plugin architecture**, OpenInk provides multi-page layout composition, sub-second universal HTTP long-polling incremental updates, dual-mode rotation (carousel/manual), and physical device interaction handling.

---

## 🌟 Core Features (v1.2)

1. **Decoupled Built-in Core vs. External Plugin Architecture (`src/plugins/`)**
   - **Built-in Core Data Sources**: Solar/Lunar calendar with Chinese Ganzhi and 24 Solar Terms (`calendar`), live weather with multi-day forecasts (`weather`), local todo management (`todo`), full-screen focus broadsheet (`focus`), and instant notification overlay (`alert`).
   - **Dynamic External Plugins**: Loaded on-demand according to `plugins.<id>.enabled` in `config.json`:
     - **P0 Plugin (`agenda`)**: Subscribes to remote `.ics` calendars (iCloud, Google Calendar, Feishu/Lark, DingTalk, Outlook, Nextcloud), calculates milestones and countdowns, and links event dots on the monthly calendar.
     - **Environment Plugin (`sensors`)**: Integrates with Home Assistant REST API for indoor room temperature, humidity, and sensor state monitoring.

2. **Multi-Page Layout Composition & Grid Reusability (`LayoutComposer`)**
   - Built-in 5 golden grid layout templates: `2|1 (left two, right one)`, `1|2 (left one, right two)`, `2×2 (four quadrants)`, `1×2 (dual column)`, and `1×1 (full-screen broadside)`.
   - Free multi-page expansion: Page 1, Page 2, Page 3... each page independently configures its grid template and widget slots.
   - Dual playlist switching: **Automatic Carousel (`carousel`)** and **Manual Pagination (`manual`)**, with interval ranges from 30 seconds up to 24 hours.

3. **Universal Pull Protocol & Long-Polling Synchronization (`/api/v1/*` + `/kiosk`)**
   - `GET /api/v1/display`: Returns playlist manifest, per-page short MD5 hashes, rotation mode, and instant alert status.
   - `GET /api/v1/wait`: `asyncio.Event`-based HTTP long-polling suspension endpoint, delivering millisecond-level responsiveness for layout updates and urgent notifications.
   - `GET /api/v1/assets/{bucket}/{filename}`: Distributes 16-level grayscale PNGs tailored for portrait hardware (`portrait`, 600×800) and landscape/web displays (`landscape`, 800×600).
   - `GET/POST /api/v1/event`: Terminal key and touch event callbacks (toggle todo, clear completed, dismiss alert, refresh data).
   - `GET /kiosk`: Zero-install full-screen Web Kiosk terminal with keyboard navigation, full-screen toggle, and interactive todo check-off.

4. **Configurable Port & Multi-Service Coexistence (`OPENINK_PORT`)**
   - Configurable listening port via the `OPENINK_PORT` environment variable (default: `8080`). Seamlessly coexists on the same Linux/Armbian host with existing services running on port 8000 (such as `esp32-gateway` or other relays).

---

## 🚀 Deployment Guide

### 1. Prerequisites & Dependencies

Supported OS: Linux / macOS, Python 3.10+, with `cairo` and `pango` system libraries installed.

```bash
# Debian / Ubuntu / Armbian system libraries
sudo apt update && sudo apt install -y python3-venv libcairo2 libpango-1.0-0 libpangocairo-1.0-0 gir1.2-pango-1.0 python3-gi-cairo fonts-wqy-microhei

# Create virtual environment (using --system-site-packages inherits system Cairo/GI bindings)
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start Service

```bash
# Local test run (listens on 0.0.0.0:8080 by default)
OPENINK_BIND=0.0.0.0 OPENINK_PORT=8080 .venv/bin/python3 web_studio.py
```

- **OpenInk Studio Management Dashboard**: `http://<SERVER_IP>:8080`
- **Web Kiosk Fullscreen Terminal**: `http://<SERVER_IP>:8080/kiosk`

### 3. Setup Systemd Service (Recommended for Production)

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

## 📱 Device Integration & Hardware Compatibility

### 1. Hanvon N516 (OpenInkpot · USB Network) One-Click Deployment
For Hanvon N516 USB Network devices, a persistent, power-efficient client daemon is provided:

```bash
# Execute deployment script from the server (installs to N516 NAND Flash via SSH)
./clients/n516-openinkpot/install_n516.sh n516
```

- **Reboot-Safe Key Injections**: On startup, the daemon dynamically creates 64-byte Linux `struct input_event` binary files in `/tmp/openink_keys/`, completely solving the reboot-loss issue on tmpfs.
- **150ms Flicker-Free In-Place Refresh**: Bypasses `madeye` memory image caches using dual-buffering and `NEXT_IMAGE` steps, achieving in-place screen updates without restarting the GUI.
- **Smart Power-Saving**: Runs long polling and image rotation only when USB network carrier is active (`carrier=1`); exits immediately into deep sleep when USB is disconnected.

### 2. Amazon Kindle & Generic Wi-Fi E-Ink Devices

> [!NOTE]
> **Kindle Compatibility Note**: While this project was initially developed and tuned on Hanvon N516, OpenInk v1.2 is built on a **hardware-agnostic Universal Pull Protocol**. Even if you haven't yet verified it on a physical Kindle, as long as you maintain a lightweight client script on a jailbroken Kindle (or other Wi-Fi e-readers such as Android e-ink devices, ESP32 boards, or TRMNL), **it is fully compatible out of the box**!

**Minimal Kindle Client Implementation**:
1. **Wi-Fi Connectivity**: Keep Kindle connected to the local Wi-Fi network.
2. **Scheduled Pull Script**: Use Kindle's built-in `curl` or `wget` (via cron or sleep loops):
   ```sh
   # 1. Fetch playlist manifest and extract image URL
   JSON=$(curl -s "http://<SERVER_IP>:8080/api/v1/display?device_id=kindle")
   IMG_URL=$(echo "$JSON" | grep -o 'http[^"]*landscape[^"]*' | head -n 1)

   # 2. Download 16-level grayscale image and render to e-ink screen
   curl -s "$IMG_URL" -o /tmp/screen.png
   eips -g /tmp/screen.png
   ```
3. **Authentication**: If deployed over public networks, append `?token=your-secret-token` or provide header `X-API-Token`.

---

## 🔒 Reverse Proxy & API Token Authentication

OpenInk defaults to **LAN Zero-Config Mode** (no password required when `OPENINK_API_TOKEN` is unset).

When exposing the service to the internet or securing external webhooks, configure the token via environment variable:

```bash
export OPENINK_API_TOKEN="your-secure-token"
```

Three credential delivery methods are supported:
1. **HTTP Header (Standard API)**: `X-API-Token: your-secure-token`
2. **Bearer Header (Standard Webhook)**: `Authorization: Bearer your-secure-token`
3. **URL Query (Embedded devices / Shortcuts)**: `?token=your-secure-token`
   - When requests include `?token=...`, the server automatically appends the token parameter to image download URLs in the playlist.

---

## 📢 Instant Alert API

OpenInk supports **sub-second interruptive high-priority alerts**. When external systems (mobile phones, Home Assistant automations, WeChat/Lark webhooks, system alerts, or iOS Shortcuts) trigger a notification, the server renders a dedicated 16-level grayscale alert broadsheet and immediately wakes up the e-ink terminal via HTTP long-polling.

### 1. Standard JSON POST (`POST /api/alert/push`)

```bash
curl -X POST http://<SERVER_IP>:8080/api/alert/push \
  -H "Content-Type: application/json" \
  -H "X-API-Token: your-secure-token" \
  -d '{
    "title": "Meeting Reminder",
    "text": "Sprint review starts in 10 minutes in Room 3. Please bring your laptop.",
    "sender": "Lark / Teams",
    "duration": 15
  }'
```

**Parameters**:
- `title` *(string)*: Alert title (e.g., `"Doorbell"`, `"Meeting Reminder"`, `"Server Alert"`).
- `text` *(string, required)*: Notification text, automatically formatted with adaptive font scaling and line wrapping.
- `sender` *(string, optional)*: Sender pill badge, default `"OpenInk"`.
- `duration` *(int, optional)*: Display duration in minutes (default 15). Automatically reverts to standard playlist rotation upon timeout.

### 2. Single-Line Quick GET (`GET /api/alert/quick`)

Convenient for **mobile browser bookmarks**, **iOS Shortcuts**, **Tasker**, or **Home Assistant `rest_command`**:

```bash
curl -G "http://<SERVER_IP>:8080/api/alert/quick" \
  --data-urlencode "title=Package Delivered" \
  --data-urlencode "text=Your delivery has arrived at the front door." \
  --data-urlencode "sender=Courier" \
  --data-urlencode "duration=20" \
  --data-urlencode "token=your-secure-token"
```

### 3. Dismissing Alerts (`POST /api/alert/dismiss` or Physical Keys)

- **HTTP Dismissal**:
  ```bash
  curl -X POST http://<SERVER_IP>:8080/api/alert/dismiss -H "X-API-Token: your-secure-token"
  # Or via quick GET:
  curl "http://<SERVER_IP>:8080/api/alert/dismiss?token=your-secure-token"
  ```
- **Physical Key Dismissal**: Press `Enter` / `Return` / `Space` on Hanvon N516 or Web Kiosk to immediately dismiss the alert and resume dashboard rotation.

---

## 🗺️ Roadmap

- **v1.2 (Current Release)**:
  - Architecture decoupling and elimination of hardware-specific hardcoded logic;
  - Universal Pull Protocol and sub-second HTTP long polling;
  - Port environment variable decoupling (`OPENINK_PORT`), coexisting with port 8000 services;
  - Extended rotation intervals up to 24 hours with chunked heartbeats;
  - Zero-install Web Kiosk terminal.
- **v1.3 (Planned · Digital Photo Frame & Gray Gallery)**:
  - **E-Ink Grayscale Album Pipeline**: JPEG/PNG upload, automatic center-crop, and 16-level grayscale quantization;
  - **Dithering Engine**: Floyd-Steinberg and Atkinson error-diffusion dithering for high-fidelity photo rendering;
  - **Mixed & Dedicated Frame Modes**: Dashboard + Photo mixed rotation, or standalone digital photo frame.
