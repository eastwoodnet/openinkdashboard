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
import hmac
import asyncio
import hashlib
import ipaddress
import threading
from typing import Dict, Any, Optional, List, Set
from fastapi import FastAPI, HTTPException, Response, Request, Query, Header
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel, Field
import uvicorn
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from config import (
    load_config,
    save_config,
    get_secret,
    normalize_dashboard_pages,
    sanitize_for_client,
    validate_external_url,
    save_env_secret,
    config_transaction,
)
from plugins.homeassistant import HomeAssistantClient
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
from scheduler import evaluate_schedule, filter_pages_for_rule, normalize_schedule_config

app = FastAPI(title="OpenInk Studio", version="1.4")

API_TOKEN = os.environ.get("OPENINK_API_TOKEN", "")
BIND_HOST = os.environ.get("OPENINK_BIND", "127.0.0.1")
BIND_PORT = int(os.environ.get("OPENINK_PORT", "8080"))
ASSETS_BASE_DIR = os.environ.get("OPENINK_ASSETS_DIR", "/tmp/openink_assets")
# 仅用于隔离设备网段：按来源 IP 豁免设备拉取接口，不接受 device_id 作为免密依据。
N516_NO_AUTH_IPS = {
    item.strip()
    for item in os.environ.get("OPENINK_N516_NO_AUTH_IPS", "").split(",")
    if item.strip()
}
STUDIO_MANAGEMENT_PREFIXES = (
    "/api/config",
    "/api/push_live",
    "/api/preview_generate",
    "/api/todos",
    "/api/device",
    "/api/ha",
    "/api/schedule",
    "/api/studio/",
)


def _parse_trusted_networks(raw: str):
    networks = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            print(f"[Auth Warning] 忽略无效 Studio 可信网段: {item}", flush=True)
    return tuple(networks)


STUDIO_TRUSTED_NETWORKS = _parse_trusted_networks(os.environ.get("OPENINK_STUDIO_TRUSTED_CIDRS", ""))


def _is_studio_management_path(path: str) -> bool:
    return any(
        path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/")
        for prefix in STUDIO_MANAGEMENT_PREFIXES
    )


def _is_trusted_studio_request(path: str, client_ip: str) -> bool:
    if not client_ip or not _is_studio_management_path(path):
        return False
    try:
        address = ipaddress.ip_address(client_ip)
        address = getattr(address, "ipv4_mapped", None) or address
        return any(address in network for network in STUDIO_TRUSTED_NETWORKS)
    except ValueError:
        return False


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
    if not hmac.compare_digest(candidate.encode("utf-8"), API_TOKEN.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


@app.middleware("http")
async def _protect_api_routes(request: Request, call_next):
    """统一保护 API 与接口文档，避免新增路由遗漏手工鉴权。"""
    path = request.url.path
    protected = path.startswith("/api/") or path in ("/docs", "/redoc", "/openapi.json")
    client = getattr(request, "client", None)
    client_ip = client.host if client else ""
    trusted_n516 = path.startswith("/api/v1/") and client_ip in N516_NO_AUTH_IPS
    trusted_studio = _is_trusted_studio_request(path, client_ip)
    if (trusted_n516 or trusted_studio) and API_TOKEN:
        # 路由内部仍有 _check_token；只在已通过来源规则的 scope 内注入内部凭证。
        headers = [
            (name, value) for name, value in request.scope.get("headers", [])
            if name.lower() != b"x-api-token"
        ]
        headers.append((b"x-api-token", API_TOKEN.encode("utf-8")))
        request.scope["headers"] = headers

    if trusted_studio and request.method not in ("GET", "HEAD", "OPTIONS"):
        # 可信网段只替代网络鉴权，不允许第三方网页借浏览器发起跨站写操作。
        sec_fetch_site = request.headers.get("sec-fetch-site", "")
        origin = request.headers.get("origin", "")
        if (sec_fetch_site and sec_fetch_site != "same-origin") or (
            origin and origin.rstrip("/") != str(request.base_url).rstrip("/")
        ):
            return JSONResponse(status_code=403, content={"detail": "Cross-site Studio request rejected"})

    if API_TOKEN and protected and not (trusted_n516 or trusted_studio):
        try:
            _check_token(
                request.headers.get("x-api-token"),
                request.headers.get("authorization"),
                request.query_params.get("token"),
            )
        except HTTPException:
            if path.startswith("/api/v1/"):
                print(f"[Auth] device request denied: path={path} client={client_ip}", flush=True)
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API token"})
    return await call_next(request)


def _validate_bind_security():
    """非回环监听必须显式配置管理 Token，防止误将免密 Studio 暴露到局域网。可通过 OPENINK_ALLOW_INSECURE_NO_AUTH=1 明确免除。"""
    if os.environ.get("OPENINK_ALLOW_INSECURE_NO_AUTH") == "1":
        return
    if API_TOKEN or BIND_HOST == "localhost":
        return
    try:
        if ipaddress.ip_address(BIND_HOST).is_loopback:
            return
    except ValueError:
        pass
    raise RuntimeError("非回环监听必须设置 OPENINK_API_TOKEN；若在受信任私有局域网运行可设置 OPENINK_ALLOW_INSECURE_NO_AUTH=1")


_cached_context: Optional[Dict[str, Any]] = None
_last_context_time: float = 0
_last_city: str = ""
_context_lock = threading.RLock()


def _todos_path() -> str:
    cfg = load_config()
    # 待办文件固定为项目根目录内的单个文件名，拒绝绝对路径与 ../ 逃逸。
    name = os.path.basename(str(cfg.get("todos_file", "todos.txt")))
    return os.path.join(BASE_DIR, name if name not in ("", ".", "..") else "todos.txt")


def _get_fresh_context_locked(force_refresh: bool = False, city_override: Optional[str] = None) -> Dict[str, Any]:
    global _cached_context, _last_context_time, _last_city
    now = time.time()
    cfg = load_config()
    city = city_override or cfg.get("city", "Beijing")

    td = load_todos(_todos_path(), max_items=50)

    if not force_refresh and _cached_context and (now - _last_context_time < 300) and (city == _last_city):
        _cached_context["todos"] = td
        _cached_context["todo"] = td
        return _cached_context

    cal = get_calendar_info()
    try:
        wtr = get_weather(city)
    except Exception:
        wtr = {
            "source": "fallback", "city": city, "desc": "天气不可用",
            "temp": "--°C", "feels_like": "--°C", "temp_range": "--°C ~ --°C",
            "humidity": "--%", "wind_cn": "--", "forecast": [], "success": False,
        }

    _cached_context = {
        "calendar": cal,
        "weather": wtr,
        "todos": td,
        "todo": td,
    }
    _cached_context.update(load_enabled_plugins_context(cfg, force_refresh=force_refresh))
    _last_context_time = now
    _last_city = city
    return _cached_context


def get_fresh_context(force_refresh: bool = False, city_override: Optional[str] = None) -> Dict[str, Any]:
    with _context_lock:
        return _get_fresh_context_locked(force_refresh=force_refresh, city_override=city_override)


# =========================================================================
# Display State & Long-Polling Manager
# =========================================================================

class DisplayStateManager:
    def __init__(self):
        self._version_seq = 0
        self.version: str = f"v{int(time.time() * 1000)}-0"
        self.playlist: List[Dict[str, Any]] = []
        self.active_page_index: int = 0
        self.alert_hash: str = ""
        self.alert_filename: str = "00_alert.png"
        self.total_bytes: int = 0
        self.connected_clients: Dict[str, Dict[str, Any]] = {}
        self._waiters: Set[asyncio.Event] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._state_lock = threading.Lock()

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
        with self._state_lock:
            self._version_seq += 1
            self.version = f"v{int(time.time() * 1000)}-{self._version_seq}"
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


def _alert_is_active() -> bool:
    return alert_state.active and not alert_state.is_expired()


def _dismiss_alert(notify: bool = True, only_if_expired: bool = False) -> bool:
    """集中清理 Alert；到期清理与发布共用渲染锁，避免误删刚发布的新通知。"""
    with _render_lock:
        if only_if_expired and not (alert_state.active and alert_state.is_expired()):
            return False
        changed = alert_state.active or bool(display_manager.alert_hash)
        alert_state.dismiss()
        display_manager.alert_hash = ""
        if changed and notify:
            display_manager.notify_all()
        return changed


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


def _get_device_rotation() -> int:
    cfg = load_config()
    return int(cfg.get("device", {}).get("rotation", 90))


def _atomic_save_png(img: Image.Image, path: str):
    """
    先写入同目录临时文件再 os.replace 原子替换，确保终端在任意时刻拉取到的都是完整 PNG，
    杜绝渲染过程中被下载到半截文件导致的花屏 / 白屏。
    """
    tmp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        img.save(tmp_path, format="PNG", optimize=True)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# 渲染互斥锁：调度线程 (asyncio.to_thread) 与 FastAPI 线程池中的同步接口可能并发触发渲染，
# 必须串行化，避免同名 PNG 被交叉写入、playlist 与磁盘文件不一致。
_render_lock = threading.RLock()


def _rotate_image_for_device(img_landscape: Image.Image, rotation: Optional[int] = None) -> Image.Image:
    if rotation is None:
        rotation = _get_device_rotation()
    if rotation == 270:
        return img_landscape.transpose(Image.Transpose.ROTATE_90)
    elif rotation == 180:
        return img_landscape.transpose(Image.Transpose.ROTATE_180)
    elif rotation == 0:
        return img_landscape
    else:  # 90° (default for N516)
        return img_landscape.transpose(Image.Transpose.ROTATE_270)


def _render_cached_pages(
    pages_data: Optional[List[Dict[str, Any]]] = None,
    city_override: Optional[str] = None,
    active_page_index: int = 0,
    force_refresh: bool = False,
    rotate_portrait: bool = True,
    notify: str = "always",
    ignore_schedule_rule: bool = False,
) -> Dict[str, Any]:
    """
    Renders the pages active in the current schedule slot into `/tmp/openink_assets/portrait/`
    (rotated 600x800 for portrait framebuffers) and `/tmp/openink_assets/landscape/`
    (unrotated 800x600 for landscape displays & Web Kiosk), computes MD5 hashes and updates `display_manager`.

    notify:
      - "always":     wake all `/api/v1/wait` clients (user-initiated actions).
      - "if_changed": wake clients only when any page hash changed (scheduled refresh; avoids useless E-Ink flashes).
      - "never":      update assets silently.
    """
    cfg = load_config()
    if not pages_data:
        pages_data = normalize_dashboard_pages(cfg)
    sched_state = evaluate_schedule(cfg)
    total_page_count = len(pages_data)
    if not ignore_schedule_rule:
        pages_data = filter_pages_for_rule(pages_data, sched_state["active_rule"])

    with _render_lock:
        return _render_pages_locked(
            cfg, sched_state, pages_data, total_page_count,
            city_override, active_page_index, force_refresh, rotate_portrait, notify,
        )


def _render_pages_locked(
    cfg: Dict[str, Any],
    sched_state: Dict[str, Any],
    pages_data: List[Dict[str, Any]],
    total_page_count: int,
    city_override: Optional[str],
    active_page_index: int,
    force_refresh: bool,
    rotate_portrait: bool,
    notify: str,
) -> Dict[str, Any]:
    old_hashes = [(it["filename"], it["hash"]) for it in display_manager.playlist]

    portrait_dir = os.path.join(ASSETS_BASE_DIR, "portrait")
    landscape_dir = os.path.join(ASSETS_BASE_DIR, "landscape")
    os.makedirs(portrait_dir, exist_ok=True)
    os.makedirs(landscape_dir, exist_ok=True)

    composer = LayoutComposer(get_profile("default"))
    context = dict(get_fresh_context(force_refresh=force_refresh, city_override=city_override))
    rotation = int(cfg.get("device", {}).get("rotation", 90))

    playlist: List[Dict[str, Any]] = []
    total_bytes = 0
    valid_filenames: Set[str] = {"00_alert.png"}

    for idx, p in enumerate(pages_data):
        fname = f"{idx + 1:02d}_page_{idx + 1}.png"
        valid_filenames.add(fname)

        portrait_path = os.path.join(portrait_dir, fname)
        landscape_path = os.path.join(landscape_dir, fname)

        img_landscape = composer.render_screen(p["template"], p["slots"], context, rotate=False)
        _atomic_save_png(img_landscape, landscape_path)
        if rotate_portrait:
            _atomic_save_png(_rotate_image_for_device(img_landscape, rotation), portrait_path)
        else:
            _atomic_save_png(img_landscape, portrait_path)

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
    new_hashes = [(it["filename"], it["hash"]) for it in playlist]
    changed = new_hashes != old_hashes
    if notify == "always" or (notify == "if_changed" and changed):
        display_manager.notify_all()

    # 渲染结果已与当前时段对齐：同步调度器的时段快照，避免 30 秒后调度器误判“时段变化”再次全量重绘、
    # 导致墨水屏在一次发布后连续闪刷两次。
    _sync_scheduler_slot(sched_state)

    return {
        "ok": True,
        "changed": changed,
        "version": display_manager.version,
        "page_count": len(playlist),
        "total_page_count": total_page_count,
        "rule_name": sched_state.get("rule_name", ""),
        "size_kb": round(total_bytes / 1024, 1),
    }


def _ensure_rendered():
    if not display_manager.playlist:
        _render_cached_pages()


# =========================================================================
# Background Time-Slot Scheduler (daily rollover, periodic refresh, DND)
# =========================================================================

SCHEDULER_TICK_SEC = 30


def _slot_key_of(st: Dict[str, Any]) -> tuple:
    return (
        st["rule_id"], st["mode"], st["carousel_interval_sec"],
        tuple(p.get("id") for p in st["active_pages"]),
    )


def _sync_scheduler_slot(st: Dict[str, Any]):
    runner = globals().get("schedule_runner")
    if runner is not None:
        import datetime as _dt
        runner.last_slot_key = _slot_key_of(st)
        if runner.last_date is None:
            runner.last_date = _dt.date.today().isoformat()
        # 手动发布也是一次完整刷新，避免排程器紧接着重复采集和重绘。
        runner.last_refresh_ts = time.time()


class ScheduleRunner:
    """
    Pure decision logic for one scheduler tick, separated from asyncio for testability.

    Rules:
    - Slot transition (rule/mode/pages/interval changed):
        * entering DND  -> do NOT re-render; only wake clients so they learn `mode=sleep_dnd` and stop flipping.
        * other slots   -> force re-render with filtered pages and wake clients.
    - Date rollover at midnight:
        * in DND        -> refresh data context in memory only (screen stays frozen, zero wear).
        * otherwise     -> force re-render; wake clients only if images changed.
    - Periodic refresh every `active_interval_sec` (skipped in DND); wake only if images changed.
    - Expired alerts are dismissed automatically.
    """

    def __init__(self):
        self.last_slot_key: Optional[tuple] = None
        self.last_date: Optional[str] = None
        self.last_refresh_ts: float = time.time()

    def tick(self, now_ts: Optional[float] = None, now_dt=None) -> str:
        import datetime as _dt
        now_ts = now_ts if now_ts is not None else time.time()
        now_dt = now_dt or _dt.datetime.now()
        cfg = load_config()
        st = evaluate_schedule(cfg, now=now_dt)
        slot_key = _slot_key_of(st)
        today = now_dt.date().isoformat()
        action = "idle"

        if alert_state.active and alert_state.is_expired():
            _dismiss_alert(only_if_expired=True)
            action = "alert_expired"

        if self.last_slot_key is None:
            # First tick after startup: assets were rendered by _ensure_rendered().
            self.last_slot_key = slot_key
            self.last_date = today
            self.last_refresh_ts = now_ts
            return action if action != "idle" else "init"

        if slot_key != self.last_slot_key:
            if st["is_dnd"]:
                self.last_slot_key = slot_key
                self.last_date = today
                display_manager.notify_all()
                return "enter_dnd"
            # 成功后才提交时段快照；失败时下一 tick 继续重试本次切换。
            _render_cached_pages(force_refresh=True, notify="always")
            self.last_slot_key = slot_key
            self.last_date = today
            self.last_refresh_ts = now_ts
            return "slot_change"

        if today != self.last_date:
            if st["is_dnd"]:
                get_fresh_context(force_refresh=True)
                self.last_date = today
                return "rollover_silent"
            _render_cached_pages(force_refresh=True, notify="if_changed")
            self.last_date = today
            self.last_refresh_ts = now_ts
            return "rollover"

        if not st["is_dnd"] and (now_ts - self.last_refresh_ts) >= st["active_interval_sec"]:
            res = _render_cached_pages(force_refresh=True, notify="if_changed")
            self.last_refresh_ts = now_ts
            return "refresh_changed" if res.get("changed") else "refresh_unchanged"

        return action


schedule_runner = ScheduleRunner()


def _schedule_status_payload(cfg: Dict[str, Any]) -> Dict[str, Any]:
    st = evaluate_schedule(cfg)
    return {
        "enabled": st["schedule_enabled"],
        "rule_id": st["rule_id"],
        "rule_name": st["rule_name"],
        "window": st["window"],
        "mode": st["mode"],
        "is_dnd": st["is_dnd"],
        "carousel_interval_sec": st["carousel_interval_sec"],
        "active_page_ids": [p.get("id") for p in st["active_pages"]],
        "next_boundary_sec": st["next_boundary_sec"],
        "active_interval_sec": st["active_interval_sec"],
    }


@app.get("/api/schedule/status")
def schedule_status_api():
    return _schedule_status_payload(load_config())


async def _scheduler_loop():
    while True:
        await asyncio.sleep(SCHEDULER_TICK_SEC)
        try:
            action = await asyncio.to_thread(schedule_runner.tick)
            if action not in ("idle", "init", "refresh_unchanged"):
                print(f"[Scheduler] {time.strftime('%Y-%m-%d %H:%M:%S')} action={action}", flush=True)
        except Exception as e:
            print(f"[Scheduler Warning] tick failed: {type(e).__name__}: {e}", flush=True)


@app.on_event("startup")
async def _start_scheduler():
    _validate_bind_security()
    display_manager.bind_loop(asyncio.get_running_loop())
    if os.environ.get("OPENINK_DISABLE_SCHEDULER") == "1":
        return
    asyncio.create_task(_scheduler_loop())


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
    homeassistant: Optional[Dict[str, Any]] = None
    rotation: Optional[int] = None
    schedule: Optional[Dict[str, Any]] = None


class HATestRequest(BaseModel):
    url: Optional[str] = None
    token: Optional[str] = None


class DeviceRotationRequest(BaseModel):
    rotation: int = Field(..., description="0, 90, 180, or 270")


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


def _validate_page_specs(pages: List[Dict[str, Any]]):
    if not 1 <= len(pages) <= 20:
        raise HTTPException(status_code=400, detail="页面数量必须为 1~20")
    ids = []
    for page in pages:
        if not isinstance(page, dict):
            raise HTTPException(status_code=400, detail="页面配置格式无效")
        pid = str(page.get("id") or "").strip()
        if not pid or len(pid) > 64 or page.get("template") not in ("2_1", "1_2", "2x2", "1x2", "1x1"):
            raise HTTPException(status_code=400, detail="页面 ID 或模板无效")
        if not isinstance(page.get("slots"), dict):
            raise HTTPException(status_code=400, detail=f"页面 {pid} 的 slots 无效")
        ids.append(pid)
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=400, detail="页面 ID 必须唯一")


def _validate_schedule_pages(schedule: Dict[str, Any], pages: List[Dict[str, Any]]):
    valid_ids = {str(p.get("id")) for p in pages}
    for rule in normalize_schedule_config(schedule)["rules"]:
        unknown = sorted(set(rule["pages"]) - valid_ids)
        if unknown:
            raise HTTPException(status_code=400, detail=f"时段 {rule['name']} 引用了不存在的页面: {', '.join(unknown)}")


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

    _validate_page_specs(pages_data)
    _validate_schedule_pages(cfg.get("schedule"), pages_data)
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

    # 发布与定时刷新统一遵循当前时段规则的页面筛选（规则 pages 为空 = 展示全部页面），
    # 避免“发布时显示全部、30 分钟后定时刷新又被规则筛掉”导致的页数来回跳变与 madeye 反复重启。
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
    sched_state = evaluate_schedule(cfg)
    mode = sched_state["mode"]
    carousel_interval_sec = int(sched_state["carousel_interval_sec"])

    if orientation == "landscape" or device_id.startswith("kiosk") or device_id.startswith("web"):
        asset_bucket = "landscape"
    else:
        asset_bucket = "portrait"

    base_url = str(request.base_url).rstrip("/")

    playlist_out = []
    for item in display_manager.playlist:
        fname = item["filename"]
        fhash = item["hash"]
        url = f"{base_url}/api/v1/assets/{asset_bucket}/{fname}?v={fhash}"
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

    alert_active = _alert_is_active()
    if sched_state["is_dnd"] and not sched_state["allow_alert_override"]:
        alert_active = False
    alert_url = ""
    if alert_active and display_manager.alert_hash:
        alert_url = f"{base_url}/api/v1/assets/{asset_bucket}/{display_manager.alert_filename}?v={display_manager.alert_hash}"

    return {
        "status": 0,
        "version": display_manager.version,
        "mode": mode,
        "refresh_rate": int(sched_state["active_interval_sec"]),
        "carousel_interval_sec": carousel_interval_sec,
        "schedule": {
            "rule_id": sched_state["rule_id"],
            "rule_name": sched_state["rule_name"],
            "window": sched_state["window"],
            "is_dnd": sched_state["is_dnd"],
            "next_boundary_sec": sched_state["next_boundary_sec"],
        },
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
    request: Request,
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
    cache_control = (
        "private, max-age=31536000, immutable"
        if request.query_params.get("v")
        else "no-cache, must-revalidate"
    )
    return FileResponse(file_path, media_type="image/png", headers={"Cache-Control": cache_control})


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
    effective_timeout = timeout
    if _alert_is_active():
        remaining = max(1, int(alert_state.expire_at - time.time()) + 1)
        effective_timeout = min(timeout, remaining)
    res = await display_manager.wait_for_change(version, effective_timeout)
    if alert_state.active and alert_state.is_expired():
        if await asyncio.to_thread(_dismiss_alert, only_if_expired=True):
            res = {"changed": True, "version": display_manager.version}
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
        # 与 Widget 一样使用“未完成在前”的显示顺序，避免按键操作原始列表中的另一项。
        items = td_data.get("items", [])
        if index <= len(items):
            target = items[index - 1]
            if mark_todo_status(_todos_path(), target["id"], done=not target["done"]):
                _render_cached_pages()
                msg = f"Toggled todo #{index}: {target['text']}"
        else:
            msg = f"Todo #{index} out of range"

    elif act == "clear_completed":
        removed = clear_completed_todos(_todos_path())
        msg = f"Cleared {removed} completed todos"
        if removed:
            _render_cached_pages()

    elif act in ("refresh", "refresh_or_dismiss"):
        if _alert_is_active():
            _dismiss_alert()
            msg = "Dismissed active alert"
        else:
            _render_cached_pages(force_refresh=True)
            msg = "Refreshed context and re-rendered pages"
    else:
        msg = f"Ignored event ({k or act})"

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
    ha_cfg = cfg.get("homeassistant", {})
    ha_token = get_secret(ha_cfg, "token")
    ha_token_masked = (ha_token[:6] + "..." + ha_token[-4:]) if len(ha_token) > 10 else ("***" if ha_token else "")
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
        "device": {
            "rotation": _get_device_rotation(),
        },
        "plugins": sanitize_for_client(cfg.get("plugins", {})),
        "plugin_catalog": PLUGIN_CATALOG,
        "enabled_plugins": get_enabled_plugin_ids(cfg),
        "homeassistant": {
            "url": ha_cfg.get("url", ""),
            "token_set": bool(ha_token),
            "token_masked": ha_token_masked,
            "sensors": ha_cfg.get("sensors", [])
        },
        "sensors": ctx.get("sensors", []),
        "agenda": ctx.get("agenda", {}),
        "schedule": normalize_schedule_config(cfg.get("schedule")),
        "schedule_status": _schedule_status_payload(cfg),
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
    pending_ha_secret: Optional[str] = None

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
            _validate_page_specs(req.pages)
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

    if req.homeassistant is not None:
        cfg = load_config()
        ha = dict(cfg.get("homeassistant", {}))
        ha_in = req.homeassistant
        if "url" in ha_in and ha_in["url"] is not None:
            raw_url = ha_in["url"].strip()
            clean_url = validate_external_url(raw_url, allow_private_lan=True) if raw_url else ""
            if raw_url and not clean_url:
                raise HTTPException(status_code=400, detail="Home Assistant URL 无效")
            ha["url"] = clean_url
        if "ca_file" in ha_in:
            ha["ca_file"] = str(ha_in.get("ca_file") or "").strip()
        if "sensors" in ha_in and isinstance(ha_in["sensors"], list):
            ha["sensors"] = ha_in["sensors"]
        token_val = ha_in.get("token")
        if token_val and not token_val.startswith("***"):
            pending_ha_secret = token_val.strip()
            ha["token_env"] = "HA_TOKEN"
        updates["homeassistant"] = ha
        force_refresh = True

    if req.sensors is not None:
        cfg = load_config()
        ha = dict(cfg.get("homeassistant", {}))
        ha["sensors"] = req.sensors
        updates["homeassistant"] = ha
        force_refresh = True

    if req.rotation is not None and req.rotation in (0, 90, 180, 270):
        updates.setdefault("device", {})["rotation"] = req.rotation
        force_refresh = True

    if req.schedule is not None:
        updates["schedule"] = normalize_schedule_config(req.schedule)

    if updates:
        with config_transaction():
            current_cfg = load_config()
            candidate_pages = normalize_dashboard_pages(
                {"dashboard": updates["dashboard"]} if "dashboard" in updates else current_cfg
            )
            candidate_schedule = updates.get("schedule", current_cfg.get("schedule"))
            _validate_schedule_pages(candidate_schedule, candidate_pages)
            if pending_ha_secret is not None:
                previous_ha_secret = get_secret(current_cfg.get("homeassistant", {}), "token")
                if not save_env_secret("HA_TOKEN", pending_ha_secret):
                    raise HTTPException(status_code=500, detail="HA Token 保存失败")
                try:
                    save_config(updates)
                except Exception as exc:
                    # 配置事务失败时恢复原凭据，避免客户端收到失败但新 Token 已生效。
                    if not save_env_secret("HA_TOKEN", previous_ha_secret):
                        raise RuntimeError("配置保存及 HA Token 回滚均失败，请立即检查 .env") from exc
                    raise
            else:
                save_config(updates)

    ctx = get_fresh_context(force_refresh=force_refresh)
    new_cfg = load_config()
    new_dash = new_cfg.get("dashboard", {})
    pages = normalize_dashboard_pages(new_cfg)
    _render_cached_pages(pages_data=pages, force_refresh=False)

    new_ha = new_cfg.get("homeassistant", {})
    new_ha_token = get_secret(new_ha, "token")
    new_ha_masked = (new_ha_token[:6] + "..." + new_ha_token[-4:]) if len(new_ha_token) > 10 else ("***" if new_ha_token else "")

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
        "device": {
            "rotation": _get_device_rotation(),
        },
        "plugins": sanitize_for_client(new_cfg.get("plugins", {})),
        "plugin_catalog": PLUGIN_CATALOG,
        "enabled_plugins": get_enabled_plugin_ids(new_cfg),
        "homeassistant": {
            "url": new_ha.get("url", ""),
            "token_set": bool(new_ha_token),
            "token_masked": new_ha_masked,
            "sensors": new_ha.get("sensors", [])
        },
        "sensors": ctx.get("sensors", []),
        "agenda": ctx.get("agenda", {}),
        "schedule": normalize_schedule_config(new_cfg.get("schedule")),
        "schedule_status": _schedule_status_payload(new_cfg),
        "weather": ctx.get("weather", {}),
        "version": display_manager.version,
    }


# =========================================================================
# Home Assistant Integration API (Test & Discovery)
# =========================================================================

@app.post("/api/ha/test")
def test_ha_connection_api(
    req: HATestRequest,
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """测试 Home Assistant 实例与 Token 连通性"""
    _check_token(x_api_token, authorization, token)
    cfg = load_config()
    ha_cfg = cfg.get("homeassistant", {})
    test_url = (req.url or ha_cfg.get("url", "")).strip()
    test_token = (req.token or get_secret(ha_cfg, "token")).strip()
    if not test_url:
        return {"ok": False, "error": "请先输入 Home Assistant 实例地址 (URL)"}
    if not test_token:
        return {"ok": False, "error": "请先输入长期访问令牌 (Token)"}
    ha = HomeAssistantClient(test_url, test_token, ca_file=ha_cfg.get("ca_file", ""))
    return ha.test_connection()


@app.get("/api/ha/entities")
def get_ha_entities_api(
    url: Optional[str] = Query(None),
    ha_token: Optional[str] = Query(None, alias="token"),
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    """获取 Home Assistant 中的所有传感器实体列表以供一键勾选"""
    _check_token(x_api_token, authorization, token)
    cfg = load_config()
    ha_cfg = cfg.get("homeassistant", {})
    target_url = (url or ha_cfg.get("url", "")).strip()
    target_token = (ha_token or get_secret(ha_cfg, "token")).strip()
    if not target_url:
        return {"ok": False, "error": "请先配置 Home Assistant 实例地址 (URL)", "entities": []}
    if not target_token:
        return {"ok": False, "error": "请先配置长期访问令牌 (Token)", "entities": []}
    ha = HomeAssistantClient(target_url, target_token, ca_file=ha_cfg.get("ca_file", ""))
    entities = ha.discover_sensors()
    return {"ok": True, "entities": entities}


# =========================================================================
# Device Rotation API (90° Standard vs 270° Inverted / 180° Flip)
# =========================================================================

@app.post("/api/device/rotation")
def set_device_rotation_api(
    req: DeviceRotationRequest,
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    if req.rotation not in (0, 90, 180, 270):
        raise HTTPException(status_code=400, detail="Rotation 必须为 0, 90, 180 或 270")
    save_config({"device": {"rotation": req.rotation}})
    res = _render_cached_pages(force_refresh=True)
    return {
        "status": "ok",
        "rotation": req.rotation,
        "message": f"设备旋转已设为 {req.rotation}°，已重新渲染并推送到墨水屏",
        "version": res["version"]
    }


@app.post("/api/device/flip180")
@app.get("/api/device/flip180")
def flip_device_180_api(
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    current_rot = _get_device_rotation()
    new_rot = 270 if current_rot == 90 else 90
    save_config({"device": {"rotation": new_rot}})
    res = _render_cached_pages(force_refresh=True)
    return {
        "status": "ok",
        "rotation": new_rot,
        "message": f"已将屏幕旋转 180° (当前为 {new_rot}°)，已重新渲染并推送到墨水屏",
        "version": res["version"]
    }


@app.post("/api/preview_generate")
def generate_preview(req: LayoutRequest):
    """
    Renders the 800×600 logical screen layout in landscape orientation (rotate=False)
    and returns PNG bytes for Web Studio preview.
    """
    composer = LayoutComposer(get_profile("default"))
    if req.alert and req.template == "1x1" and req.slots.get("full") == "alert":
        # 纯通知预览不依赖天气、HA 或 ICS，避免本地排版编辑被外部采集阻塞。
        context = {"alert": req.alert}
    else:
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
        "total_page_count": res.get("total_page_count", res["page_count"]),
        "rule_name": res.get("rule_name", ""),
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

@app.get("/api/studio/alert/status")
@app.get("/api/alert/status")
def alert_status():
    active = _alert_is_active()
    return {
        "active": active,
        "title": alert_state.title if active else "",
        "text": alert_state.text if active else "",
        "sender": alert_state.sender if active else "",
        "remaining_sec": max(0, int(alert_state.expire_at - time.time())) if active else 0
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


@app.post("/api/studio/alert/push")
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

    with _render_lock:
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
            rotate=False
        )
        _atomic_save_png(img_landscape, landscape_alert_png)
        _atomic_save_png(_rotate_image_for_device(img_landscape), portrait_alert_png)

        # 资产完整发布后再提交状态，失败时不会留下 active 但无图片的 Alert。
        alert_state.set_alert(req.title, req.text, req.sender, req.duration)
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


@app.post("/api/studio/alert/dismiss")
@app.post("/api/alert/dismiss")
def alert_dismiss_post(
    token: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_token(x_api_token, authorization, token)
    _dismiss_alert()
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
    _validate_bind_security()
    _ensure_rendered()
    uvicorn.run(app, host=BIND_HOST, port=BIND_PORT, log_level="warning")
