#!/usr/bin/env python3
"""
OpenInk Studio & Universal Display Server
=========================================
- 内置核心数据源 (calendar, weather, todo, focus, alert) + 外部插件数据源按需加载；
- 支持多页看板自由编排、自动轮播 (carousel) 与手动翻页 (manual)；
- 提供标准拉取清单 (/api/v1/display)、长轮询同步 (/api/v1/wait)、事件回调 (/api/v1/event) 与 Web Kiosk (/kiosk)。
"""

import os
import io
import sys
import time
import asyncio
import hashlib
from typing import Dict, Any, Optional, List, Set
from fastapi import FastAPI, HTTPException, Response, Request, Query, Header
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
import uvicorn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from config import load_config, save_config, get_secret, normalize_dashboard_pages
from profiles import get_profile
from layout_composer import LayoutComposer
from calendar_info import get_calendar_info
from weather import get_weather
from todos import (
    load_todos,
    add_todo_item,
    mark_todo_status,
    delete_todo_item,
    clear_completed_todos,
)
from plugins import PLUGIN_CATALOG, get_enabled_plugin_ids, load_enabled_plugins_context
from alert_state import alert_state

app = FastAPI(title="OpenInk Studio")

API_TOKEN = os.environ.get("OPENINK_API_TOKEN", "")
BIND_HOST = os.environ.get("OPENINK_BIND", "0.0.0.0")
ASSETS_BASE_DIR = "/tmp/openink_assets"


def _check_token(
    x_api_token: Optional[str] = None,
    authorization: Optional[str] = None,
    query_token: Optional[str] = None,
):
    """
    校验 API Token（当环境变量 OPENINK_API_TOKEN 设置时生效）。
    支持三种传入方式以适配 Web 面板、Wi-Fi 墨水屏终端（如 Kindle/ESP32）及外部 Webhook：
      1. Header `X-API-Token: <token>`
      2. Header `Authorization: Bearer <token>`
      3. URL Query `?token=<token>`
    """
    if not API_TOKEN:
        return
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    candidate = x_api_token or bearer or query_token or ""
    if candidate != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


_cached_context: Optional[Dict[str, Any]] = None
_last_context_time: float = 0
_last_city: str = ""


def _todos_path() -> str:
    cfg = load_config()
    return os.path.join(BASE_DIR, cfg.get("todos_file", "todos.txt"))


def get_fresh_context(force_refresh: bool = False, city_override: Optional[str] = None) -> Dict[str, Any]:
    global _cached_context, _last_context_time, _last_city
    now = time.time()
    cfg = load_config()
    city = city_override or cfg.get("city", "Beijing")

    td = load_todos(_todos_path(), max_items=50)
    plugin_ctx = load_enabled_plugins_context(cfg, force_refresh=force_refresh)

    if not force_refresh and _cached_context and (now - _last_context_time < 300) and (city == _last_city):
        _cached_context["todos"] = td
        _cached_context["todo"] = td
        for cat in PLUGIN_CATALOG:
            _cached_context.pop(cat["id"], None)
        _cached_context.update(plugin_ctx)
        return _cached_context

    cal = get_calendar_info()
    try:
        wtr = get_weather(city)
    except Exception:
        wtr = {
            "city": city,
            "desc": "晴朗",
            "temp": "18°C",
            "feels_like": "17°C",
            "temp_range": "11°C ~ 20°C",
            "humidity": "42%",
            "wind_cn": "东北风 2级"
        }

    _cached_context = {
        "calendar": cal,
        "weather": wtr,
        "todos": td,
        "todo": td,
    }
    _cached_context.update(plugin_ctx)
    _last_context_time = now
    _last_city = city
    return _cached_context


# =========================================================================
# Display State & Long-Polling Manager
# =========================================================================

class DisplayStateManager:
    def __init__(self):
        self.version: str = f"v{int(time.time() * 1000)}"
        self.playlist: List[Dict[str, Any]] = []
        self.active_page_index: int = 0
        self.alert_hash: str = ""
        self.alert_filename: str = "00_alert.png"
        self.total_bytes: int = 0
        self.connected_clients: Dict[str, Dict[str, Any]] = {}
        self._waiters: Set[asyncio.Event] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def record_client(self, device_id: str, client_ip: str, mode: str = "pull"):
        self.connected_clients[device_id] = {
            "device_id": device_id,
            "ip": client_ip,
            "mode": mode,
            "last_seen": time.time(),
        }

    def active_clients(self, max_age_sec: int = 120) -> List[Dict[str, Any]]:
        now = time.time()
        return [
            info for info in self.connected_clients.values()
            if (now - info["last_seen"]) <= max_age_sec
        ]

    def notify_all(self):
        self.version = f"v{int(time.time() * 1000)}"
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._wake_events)
        else:
            self._wake_events()

    def _wake_events(self):
        for ev in list(self._waiters):
            ev.set()

    async def wait_for_change(self, client_version: str, timeout: int) -> Dict[str, Any]:
        self.bind_loop(asyncio.get_running_loop())
        if client_version and client_version != self.version:
            return {"changed": True, "version": self.version}

        ev = asyncio.Event()
        self._waiters.add(ev)
        try:
            await asyncio.wait_for(ev.wait(), timeout=max(1, min(timeout, 300)))
            return {"changed": True, "version": self.version}
        except asyncio.TimeoutError:
            return {"changed": False, "version": self.version}
        finally:
            self._waiters.discard(ev)


display_manager = DisplayStateManager()


def _file_md5_short(path: str) -> str:
    if not os.path.exists(path):
        return ""
    h = hashlib.md5()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()[:8]


def _normalize_bucket(bucket: str) -> str:
    if bucket in ("landscape", "kiosk", "web"):
        return "landscape"
    return "portrait"


def _render_cached_pages(
    pages_data: Optional[List[Dict[str, Any]]] = None,
    city_override: Optional[str] = None,
    active_page_index: int = 0,
    force_refresh: bool = False,
    rotate_portrait: bool = True,
) -> Dict[str, Any]:
    """
    Renders all configured pages into `/tmp/openink_assets/portrait/` (rotated 600x800 for portrait framebuffers)
    and `/tmp/openink_assets/landscape/` (unrotated 800x600 for landscape displays & Web Kiosk),
    computes MD5 hashes, updates `display_manager`, and wakes all `/api/v1/wait` clients.
    """
    cfg = load_config()
    if not pages_data:
        pages_data = normalize_dashboard_pages(cfg)

    portrait_dir = os.path.join(ASSETS_BASE_DIR, "portrait")
    landscape_dir = os.path.join(ASSETS_BASE_DIR, "landscape")
    os.makedirs(portrait_dir, exist_ok=True)
    os.makedirs(landscape_dir, exist_ok=True)

    composer = LayoutComposer(get_profile("default"))
    context = dict(get_fresh_context(force_refresh=force_refresh, city_override=city_override))

    playlist: List[Dict[str, Any]] = []
    total_bytes = 0
    valid_filenames: Set[str] = {"00_alert.png"}

    for idx, p in enumerate(pages_data):
        fname = f"{idx + 1:02d}_page_{idx + 1}.png"
        valid_filenames.add(fname)

        portrait_path = os.path.join(portrait_dir, fname)
        landscape_path = os.path.join(landscape_dir, fname)

        img_landscape = composer.render_screen(p["template"], p["slots"], context, output_path=landscape_path, rotate=False)
        if rotate_portrait:
            from PIL import Image
            img_rotated = img_landscape.transpose(Image.Transpose.ROTATE_270)
            img_rotated.save(portrait_path, optimize=True)
        else:
            img_landscape.save(portrait_path, optimize=True)

        fsize = os.path.getsize(portrait_path)
        total_bytes += fsize
        fhash = _file_md5_short(portrait_path)

        playlist.append({
            "index": idx + 1,
            "id": p.get("id", f"page_{idx + 1}"),
            "title": p.get("title", f"第 {idx + 1} 页"),
            "template": p.get("template", "2_1"),
            "filename": fname,
            "hash": fhash,
            "size_bytes": fsize,
        })

    for d in (portrait_dir, landscape_dir):
        for existing in os.listdir(d):
            if existing.endswith(".png") and existing not in valid_filenames:
                try:
                    os.remove(os.path.join(d, existing))
                except OSError:
                    pass

    display_manager.playlist = playlist
    display_manager.active_page_index = max(0, min(active_page_index, len(playlist) - 1))
    display_manager.total_bytes = total_bytes
    display_manager.notify_all()

    return {
        "ok": True,
        "version": display_manager.version,
        "page_count": len(playlist),
        "size_kb": round(total_bytes / 1024, 1),
    }


def _ensure_rendered():
    if not display_manager.playlist:
        _render_cached_pages()


# =========================================================================
# Request / Response Models
# =========================================================================

class PageSpecModel(BaseModel):
    id: str = "page_1"
    title: str = "第 1 页 · 主看板"
    template: str = "2_1"
    slots: Dict[str, str] = {
        "top_left": "calendar",
        "bottom_left": "weather",
        "right": "todo"
    }


class LayoutRequest(BaseModel):
    template: str = "2_1"
    slots: Dict[str, str] = {
        "top_left": "calendar",
        "bottom_left": "weather",
        "right": "todo"
    }
    mode: Optional[str] = None
    carousel_interval_sec: Optional[int] = None
    pages: Optional[List[PageSpecModel]] = None
    active_page_index: int = 0
    city: Optional[str] = None
    alert: Optional[Dict[str, Any]] = None


class ConfigUpdateRequest(BaseModel):
    city: Optional[str] = None
    mode: Optional[str] = None
    carousel_interval_sec: Optional[int] = None
    template: Optional[str] = None
    slots: Optional[Dict[str, str]] = None
    pages: Optional[List[Dict[str, Any]]] = None
    plugins: Optional[Dict[str, Any]] = None
    sensors: Optional[List[Dict[str, str]]] = None


class AlertRequest(BaseModel):
    title: str = Field("桌面备忘提醒", max_length=60)
    text: str = Field(..., max_length=500)
    sender: str = Field("OpenInk", max_length=30)
    duration: int = Field(15, ge=1, le=120)


class TodoAddRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=200)


class TodoItemRequest(BaseModel):
    id: int
    done: Optional[bool] = None


class DeviceEventRequest(BaseModel):
    device_id: str = "default"
    key: Optional[str] = None
    action: Optional[str] = None
    index: Optional[int] = None


_last_push_req: Optional[LayoutRequest] = None


def _do_publish_pages(req: LayoutRequest) -> Dict[str, Any]:
    cfg = load_config()
    dash_cfg = cfg.get("dashboard", {})

    if req.pages and len(req.pages) > 0:
        pages_data = [p.model_dump() for p in req.pages]
    else:
        pages_data = [
            {
                "id": "page_1",
                "title": "第 1 页 · 主看板",
                "template": req.template,
                "slots": req.slots
            }
        ]

    mode = req.mode or dash_cfg.get("mode", "carousel")
    interval_sec = req.carousel_interval_sec or int(dash_cfg.get("carousel_interval_sec", 60))

    updates: Dict[str, Any] = {
        "dashboard": {
            "mode": mode,
            "carousel_interval_sec": interval_sec,
            "template": pages_data[0]["template"],
            "slots": pages_data[0]["slots"],
            "pages": pages_data
        }
    }
    if req.city:
        updates["city"] = req.city
    save_config(updates)

    return _render_cached_pages(
        pages_data=pages_data,
        city_override=req.city,
        active_page_index=req.active_page_index,
    )


# =========================================================================
# Web Studio & Web Kiosk HTML Routes
# =========================================================================

@app.get("/", response_class=HTMLResponse)
def index_page():
    _ensure_rendered()
    html_path = os.path.join(BASE_DIR, "templates", "studio.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Studio HTML not found</h1>"


@app.get("/kiosk", response_class=HTMLResponse)
def kiosk_page():
    _ensure_rendered()
    html_path = os.path.join(BASE_DIR, "templates", "kiosk.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Kiosk HTML not found</h1>"


# =========================================================================
# Universal Pull Protocol & Long-Polling API (/api/v1/*)
# =========================================================================

@app.get("/api/v1/display")
def api_v1_display(
    request: Request,
    device_id: str = Query("default", description="终端设备标识"),
    orientation: Optional[str] = Query(None, description="画面方向: portrait(旋转) / landscape(横屏)"),
    token: Optional[str] = Query(None, description="可选 API Token (适配 Wi-Fi 墨水屏终端)"),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    _ensure_rendered()
    client_ip = request.client.host if request.client else "unknown"
    display_manager.record_client(device_id, client_ip, mode="pull")

    cfg = load_config()
    dash = cfg.get("dashboard", {})
    mode = dash.get("mode", "carousel")
    carousel_interval_sec = int(dash.get("carousel_interval_sec", 60))

    if orientation == "landscape" or device_id.startswith("kiosk") or device_id.startswith("web"):
        asset_bucket = "landscape"
    else:
        asset_bucket = "portrait"

    base_url = str(request.base_url).rstrip("/")
    token_suffix = f"&token={token}" if token else ""

    playlist_out = []
    for item in display_manager.playlist:
        fname = item["filename"]
        fhash = item["hash"]
        url = f"{base_url}/api/v1/assets/{asset_bucket}/{fname}?v={fhash}{token_suffix}"
        playlist_out.append({
            "index": item["index"],
            "id": item["id"],
            "title": item["title"],
            "filename": fname,
            "hash": fhash,
            "url": url,
        })

    active_idx = max(0, min(display_manager.active_page_index, len(playlist_out) - 1)) if playlist_out else 0
    current_item = playlist_out[active_idx] if playlist_out else {
        "index": 1,
        "id": "page_1",
        "filename": "01_page_1.png",
        "hash": "",
        "url": "",
    }

    alert_active = alert_state.active
    alert_url = ""
    if alert_active and display_manager.alert_hash:
        alert_url = f"{base_url}/api/v1/assets/{asset_bucket}/{display_manager.alert_filename}?v={display_manager.alert_hash}{token_suffix}"

    return {
        "status": 0,
        "version": display_manager.version,
        "mode": mode,
        "refresh_rate": 300,
        "carousel_interval_sec": carousel_interval_sec,
        "alert": {
            "active": alert_active,
            "beep": True,
            "title": alert_state.title if alert_active else "",
            "text": alert_state.text if alert_active else "",
            "sender": alert_state.sender if alert_active else "",
            "remaining_sec": max(0, int(alert_state.expire_at - time.time())) if alert_active else 0,
            "filename": display_manager.alert_filename,
            "hash": display_manager.alert_hash if alert_active else "",
            "url": alert_url,
        },
        "current": current_item,
        "playlist": playlist_out,
    }


@app.get("/api/v1/assets/{bucket}/{filename}")
def api_v1_asset(
    bucket: str,
    filename: str,
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    _ensure_rendered()
    norm_bucket = _normalize_bucket(bucket)
    safe_name = os.path.basename(filename)
    file_path = os.path.join(ASSETS_BASE_DIR, norm_bucket, safe_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Asset not found: {safe_name}")
    return FileResponse(
        file_path,
        media_type="image/png",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/api/v1/wait")
async def api_v1_wait(
    request: Request,
    device_id: str = Query("default"),
    version: str = Query(""),
    timeout: int = Query(60, ge=1, le=300),
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    _ensure_rendered()
    client_ip = request.client.host if request.client else "unknown"
    display_manager.record_client(device_id, client_ip, mode="longpoll")
    res = await display_manager.wait_for_change(version, timeout)
    display_manager.record_client(device_id, client_ip, mode="longpoll")
    return res


def _handle_device_event(device_id: str, key: Optional[str], action: Optional[str], index: Optional[int]) -> Dict[str, Any]:
    k = (key or "").upper().strip()
    act = (action or "").lower().strip()

    if k in ("KEY_1", "KEY_2", "KEY_3", "KEY_4", "KEY_5", "KEY_6", "KEY_7", "KEY_8", "KEY_9"):
        act = "toggle_todo"
        index = int(k.split("_")[1])
    elif k == "KEY_0":
        act = "clear_completed"
    elif k in ("KEY_ENTER", "RETURN"):
        act = "refresh_or_dismiss"

    msg = "no-op"
    if act == "toggle_todo" and index is not None and 1 <= index <= 9:
        td_data = load_todos(_todos_path(), max_items=50)
        items = td_data.get("all_items", [])
        if index <= len(items):
            target = items[index - 1]
            mark_todo_status(_todos_path(), target["id"], done=not target["done"])
            msg = f"Toggled todo #{index}: {target['text']}"
        else:
            msg = f"Todo #{index} out of range"
        _render_cached_pages()

    elif act == "clear_completed":
        removed = clear_completed_todos(_todos_path())
        msg = f"Cleared {removed} completed todos"
        _render_cached_pages()

    elif act in ("refresh", "refresh_or_dismiss"):
        if alert_state.active:
            alert_state.dismiss()
            display_manager.alert_hash = ""
            display_manager.notify_all()
            msg = "Dismissed active alert"
        else:
            _render_cached_pages(force_refresh=True)
            msg = "Refreshed context and re-rendered pages"
    else:
        _render_cached_pages()
        msg = f"Processed event ({k or act})"

    return {
        "status": "ok",
        "device_id": device_id,
        "message": msg,
        "version": display_manager.version,
    }


@app.get("/api/v1/event")
def api_v1_event_get(
    request: Request,
    device_id: str = Query("default"),
    key: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    index: Optional[int] = Query(None),
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    client_ip = request.client.host if request.client else "unknown"
    display_manager.record_client(device_id, client_ip, mode="event")
    return _handle_device_event(device_id, key, action, index)


@app.post("/api/v1/event")
def api_v1_event_post(
    req: DeviceEventRequest,
    request: Request,
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    client_ip = request.client.host if request.client else "unknown"
    display_manager.record_client(req.device_id, client_ip, mode="event")
    return _handle_device_event(req.device_id, req.key, req.action, req.index)


# =========================================================================
# Studio Configuration & Preview API
# =========================================================================

@app.get("/api/config")
def get_config_api():
    cfg = load_config()
    ctx = get_fresh_context()
    dash = cfg.get("dashboard", {})
    pages = normalize_dashboard_pages(cfg)
    return {
        "city": cfg.get("city", "Beijing"),
        "auth_required": bool(API_TOKEN),
        "dashboard": {
            "mode": dash.get("mode", "carousel"),
            "carousel_interval_sec": int(dash.get("carousel_interval_sec", 60)),
            "template": pages[0]["template"],
            "slots": pages[0]["slots"],
            "pages": pages
        },
        "plugins": cfg.get("plugins", {}),
        "plugin_catalog": PLUGIN_CATALOG,
        "enabled_plugins": get_enabled_plugin_ids(cfg),
        "sensors": ctx.get("sensors", []),
        "agenda": ctx.get("agenda", {}),
        "version": display_manager.version,
    }


@app.post("/api/config")
def update_config_api(
    req: ConfigUpdateRequest,
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    updates: Dict[str, Any] = {}
    force_refresh = False

    if req.city is not None and req.city.strip():
        updates["city"] = req.city.strip()
        force_refresh = True

    if any(x is not None for x in (req.pages, req.template, req.slots, req.mode, req.carousel_interval_sec)):
        cfg = load_config()
        dash = dict(cfg.get("dashboard", {}))
        if req.mode in ("carousel", "manual"):
            dash["mode"] = req.mode
        if req.carousel_interval_sec is not None:
            dash["carousel_interval_sec"] = max(5, min(int(req.carousel_interval_sec), 86400))
        if req.pages is not None and len(req.pages) > 0:
            dash["pages"] = req.pages
            dash["template"] = req.pages[0].get("template", "2_1")
            dash["slots"] = req.pages[0].get("slots", {})
        else:
            if req.template is not None:
                dash["template"] = req.template
            if req.slots is not None:
                dash["slots"] = req.slots
            pages = normalize_dashboard_pages({"dashboard": dash})
            pages[0]["template"] = dash.get("template", "2_1")
            pages[0]["slots"] = dash.get("slots", {})
            dash["pages"] = pages
        updates["dashboard"] = dash

    if req.plugins is not None:
        cfg = load_config()
        cur_plugins = dict(cfg.get("plugins", {}))
        for pid, pval in req.plugins.items():
            if isinstance(pval, dict) and isinstance(cur_plugins.get(pid), dict):
                merged_p = dict(cur_plugins[pid])
                merged_p.update(pval)
                cur_plugins[pid] = merged_p
            else:
                cur_plugins[pid] = pval
        updates["plugins"] = cur_plugins
        force_refresh = True

    if req.sensors is not None:
        cfg = load_config()
        ha = dict(cfg.get("homeassistant", {}))
        ha["sensors"] = req.sensors
        updates["homeassistant"] = ha

    if updates:
        save_config(updates)

    ctx = get_fresh_context(force_refresh=force_refresh)
    new_cfg = load_config()
    new_dash = new_cfg.get("dashboard", {})
    pages = normalize_dashboard_pages(new_cfg)
    _render_cached_pages(pages_data=pages, force_refresh=False)

    return {
        "status": "ok",
        "city": new_cfg.get("city", "Beijing"),
        "dashboard": {
            "mode": new_dash.get("mode", "carousel"),
            "carousel_interval_sec": int(new_dash.get("carousel_interval_sec", 60)),
            "template": pages[0]["template"],
            "slots": pages[0]["slots"],
            "pages": pages
        },
        "plugins": new_cfg.get("plugins", {}),
        "plugin_catalog": PLUGIN_CATALOG,
        "enabled_plugins": get_enabled_plugin_ids(new_cfg),
        "sensors": ctx.get("sensors", []),
        "agenda": ctx.get("agenda", {}),
        "weather": ctx.get("weather", {}),
        "version": display_manager.version,
    }


@app.post("/api/preview_generate")
def generate_preview(req: LayoutRequest):
    """
    Renders the 800×600 logical screen layout in landscape orientation (rotate=False)
    and returns PNG bytes for Web Studio preview.
    """
    composer = LayoutComposer(get_profile("default"))
    context = dict(get_fresh_context(city_override=req.city))
    if req.alert:
        context["alert"] = req.alert
    else:
        context.pop("alert", None)

    img = composer.render_screen(req.template, req.slots, context, rotate=False)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Response(content=buf.getvalue(), media_type="image/png")


@app.post("/api/push_live")
def push_live(
    req: LayoutRequest,
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    global _last_push_req
    _last_push_req = req

    res = _do_publish_pages(req)
    clients = display_manager.active_clients()
    return {
        "status": "ok",
        "message": "Published",
        "version": res["version"],
        "page_count": res["page_count"],
        "size_kb": res["size_kb"],
        "connected_clients": len(clients),
    }


# =========================================================================
# Online Todo List Management API
# =========================================================================

@app.get("/api/todos")
def get_todos_api():
    return load_todos(_todos_path(), max_items=50)


@app.post("/api/todos/add")
def add_todo_api(
    req: TodoAddRequest,
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    add_todo_item(_todos_path(), req.text.strip())
    _render_cached_pages()
    return load_todos(_todos_path(), max_items=50)


@app.post("/api/todos/toggle")
def toggle_todo_api(
    req: TodoItemRequest,
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    data = load_todos(_todos_path(), max_items=50)
    target = next((it for it in data.get("all_items", []) if it["id"] == req.id), None)
    if not target:
        raise HTTPException(status_code=404, detail="未找到该待办项")
    new_done = (not target["done"]) if req.done is None else bool(req.done)
    mark_todo_status(_todos_path(), req.id, done=new_done)
    _render_cached_pages()
    return load_todos(_todos_path(), max_items=50)


@app.post("/api/todos/delete")
def delete_todo_api(
    req: TodoItemRequest,
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    if not delete_todo_item(_todos_path(), req.id):
        raise HTTPException(status_code=404, detail="未找到该待办项")
    _render_cached_pages()
    return load_todos(_todos_path(), max_items=50)


@app.post("/api/todos/clear")
def clear_todos_api(
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    clear_completed_todos(_todos_path())
    _render_cached_pages()
    return load_todos(_todos_path(), max_items=50)


# =========================================================================
# Alert / Instant Notification API
# =========================================================================

@app.get("/api/alert/status")
def alert_status():
    return {
        "active": alert_state.active,
        "title": alert_state.title,
        "text": alert_state.text,
        "sender": alert_state.sender,
        "remaining_sec": max(0, int(alert_state.expire_at - time.time())) if alert_state.active else 0
    }


@app.get("/api/device_status")
def device_status():
    cfg = load_config()
    clients = display_manager.active_clients(max_age_sec=120)
    hw_client = next((c for c in clients if not c["device_id"].startswith("web")), None)
    online = len(clients) > 0

    return {
        "online": online,
        "pull_active": hw_client is not None or len(clients) > 0,
        "connected_clients": clients,
        "auth_required": bool(API_TOKEN),
        "version": display_manager.version,
        "host": cfg["device"].get("host", "192.168.111.1"),
        "profile": "OpenInk 800×600 · 16级灰阶"
    }


@app.post("/api/alert/push")
def alert_push(
    req: AlertRequest,
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="缺少 text 正文字段")

    alert_state.set_alert(req.title, req.text, req.sender, req.duration)

    portrait_dir = os.path.join(ASSETS_BASE_DIR, "portrait")
    landscape_dir = os.path.join(ASSETS_BASE_DIR, "landscape")
    os.makedirs(portrait_dir, exist_ok=True)
    os.makedirs(landscape_dir, exist_ok=True)

    composer = LayoutComposer(get_profile("default"))
    landscape_alert_png = os.path.join(landscape_dir, "00_alert.png")
    portrait_alert_png = os.path.join(portrait_dir, "00_alert.png")

    img_landscape = composer.render_alert_screen(
        title=req.title,
        text=req.text,
        sender=req.sender,
        duration_min=req.duration,
        output_path=landscape_alert_png,
        rotate=False
    )
    from PIL import Image
    img_rotated = img_landscape.transpose(Image.Transpose.ROTATE_270)
    img_rotated.save(portrait_alert_png, optimize=True)

    display_manager.alert_hash = _file_md5_short(portrait_alert_png)
    display_manager.notify_all()

    return {
        "status": "ok",
        "message": f"通知已发布，展示时长 {req.duration} 分钟",
        "version": display_manager.version,
        "alert": {
            "title": req.title,
            "text": req.text,
            "sender": req.sender,
            "duration_min": req.duration,
            "hash": display_manager.alert_hash,
        }
    }


@app.get("/api/alert/quick")
def alert_push_get(
    text: str = Query(..., description="通知正文"),
    title: str = Query("桌面备忘提醒", description="通知标题"),
    sender: str = Query("OpenInk", description="来源"),
    duration: int = Query(15, description="展示时长(分钟)"),
    token: Optional[str] = Query(None, description="可选 API Token"),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    req = AlertRequest(title=title, text=text, sender=sender, duration=duration)
    return alert_push(req, token=token, x_api_token=x_api_token, authorization=authorization)


@app.post("/api/alert/dismiss")
def alert_dismiss_post(
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    alert_state.dismiss()
    display_manager.alert_hash = ""
    _render_cached_pages()
    return {
        "status": "ok",
        "version": display_manager.version,
        "message": "通知已解除，已恢复常规看板"
    }


@app.get("/api/alert/dismiss")
def alert_dismiss_get(
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    return alert_dismiss_post(token=token, x_api_token=x_api_token, authorization=authorization)


if __name__ == "__main__":
    _ensure_rendered()
    uvicorn.run(app, host=BIND_HOST, port=8000, log_level="warning")
