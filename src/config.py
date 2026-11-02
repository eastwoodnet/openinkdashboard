"""
统一配置加载、持久化与安全脱敏模块 (v1.4).

- 本地 `config.json` 已被 `.gitignore` 隔离，绝不入库；
- 仓库仅保留脱敏模板 `config.example.json`；
- 敏感凭据一律通过环境变量注入（HA_TOKEN / N516_PASSWORD / OPENINK_API_TOKEN），严禁明文落盘。
"""

import os
import json
import ipaddress
import re
import socket
import threading
import urllib.parse
from contextlib import contextmanager
from typing import Dict, Any, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
EXAMPLE_CONFIG_PATH = os.path.join(BASE_DIR, "config.example.json")
ENV_PATH = os.path.join(BASE_DIR, ".env")

def load_dotenv():
    """轻量读取本地 .env 文件至环境变量（无需第三方外部依赖库）。"""
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception as e:
            print(f"[Config Warning] 读取 .env 失败: {e}")

load_dotenv()

SENSITIVE_KEYS = {"token", "password", "secret", "api_key", "private_key", "access_token"}

DEFAULT_CONFIG: Dict[str, Any] = {
    "city": "Beijing",
    "dashboard": {
        "mode": "carousel",
        "carousel_interval_sec": 60,
        "template": "2_1",
        "slots": {
            "top_left": "calendar",
            "bottom_left": "weather",
            "right": "todo"
        },
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
            "enabled": True,
            "ics_urls": [],
            "items": [
                {
                    "title": "OpenInk 里程碑发布",
                    "date": "+6",
                    "time": "全天",
                    "is_countdown": True
                },
                {
                    "title": "架构评审与墨水屏实机联调",
                    "date": "+0",
                    "time": "15:00",
                    "is_countdown": False
                },
                {
                    "title": "外部 ICS 日历同步功能验收",
                    "date": "+1",
                    "time": "10:30",
                    "is_countdown": False
                }
            ]
        },
        "sensors": {
            "enabled": True
        }
    },
    "device": {
        "host": "192.168.111.1",
        "port": 22,
        "user": "root",
        "password_env": "OPENINK_DEVICE_PASSWORD",
        "ssh_alias": "eink",
        "dashboard_dir": "/tmp/dashboard",
        "rotation": 90
    },
    "todos_file": "todos.txt",
    "font_family": "WenQuanYi Micro Hei, Segoe UI Emoji, Maple Mono NF CN, Noto Color Emoji, Segoe UI Symbol, sans-serif",
    "card_shadow": True,
    "shadow_offset": 5,
    "shadow_gray": 0.42,
    "homeassistant": {
        "url": "",
        "token_env": "HA_TOKEN",
        "sensors": []
    }
}


def _merge(base: dict, override: dict) -> dict:
    """浅层 dict 递归合并，override 优先。"""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _strip_plaintext_secrets(obj: Any) -> Any:
    """递归剥离任何字典中的明文密钥字段，防止意外写入磁盘。"""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            if k.lower() in SENSITIVE_KEYS:
                continue
            cleaned[k] = _strip_plaintext_secrets(v)
        return cleaned
    elif isinstance(obj, list):
        return [_strip_plaintext_secrets(item) for item in obj]
    return obj


def sanitize_for_client(obj: Any) -> Any:
    """对返回给前端 API 的配置数据进行递归脱敏掩码。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in SENSITIVE_KEYS and isinstance(v, str) and v:
                out[k] = "***"
            else:
                out[k] = sanitize_for_client(v)
        return out
    elif isinstance(obj, list):
        return [sanitize_for_client(item) for item in obj]
    return obj


def mask_url_for_log(url: str) -> str:
    """日志输出时隐藏 URL 路径与查询参数中的敏感 Token。"""
    try:
        parsed = urllib.parse.urlsplit(url.strip())
        if parsed.scheme and parsed.netloc:
            host = parsed.hostname or parsed.netloc
            return f"{parsed.scheme}://{host}/***"
    except Exception:
        pass
    return "<masked-url>"


def _is_blocked_address(address: str, allow_private_lan: bool) -> bool:
    """判断解析后的 IP 是否可用于外部采集；私网仅对明确的 HA 管理配置开放。"""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    if ip.is_unspecified or ip.is_multicast or ip.is_reserved:
        return True
    if allow_private_lan:
        return False
    # 非公网地址一律拒绝，覆盖 CGNAT、文档段、保留段及各类内部地址。
    return not ip.is_global


def validate_external_url(
    raw_url: str,
    allow_private_lan: bool = False,
    resolve: bool = False,
) -> str:
    """
    校验采集 URL。默认拒绝私网、回环和链路本地地址；resolve=True 时同时检查全部 DNS 结果。
    每次重定向都必须重新调用本函数，不能只校验初始 URL。
    """
    clean = (raw_url or "").strip()
    if not clean:
        return ""
    if clean.startswith("webcal://"):
        clean = "https://" + clean[len("webcal://"):]
    try:
        parsed = urllib.parse.urlsplit(clean)
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
            return ""
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host or parsed.fragment:
            return ""
        port = parsed.port
    except (ValueError, TypeError):
        return ""

    if host == "localhost" or host.endswith(".localhost") or host == "metadata.google.internal":
        if not allow_private_lan:
            return ""
    try:
        ipaddress.ip_address(host)
        if _is_blocked_address(host, allow_private_lan):
            return ""
    except ValueError:
        pass

    if resolve:
        return resolve_external_url(clean, allow_private_lan=allow_private_lan)[0]
    return clean


def resolve_external_url(raw_url: str, allow_private_lan: bool = False) -> tuple[str, list[str]]:
    """一次完成 URL 校验和 DNS 解析，供连接层固定使用同一批 IP，避免二次解析。"""
    clean = validate_external_url(raw_url, allow_private_lan=allow_private_lan, resolve=False)
    if not clean:
        return "", []
    parsed = urllib.parse.urlsplit(clean)
    host = (parsed.hostname or "").lower().rstrip(".")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            addresses = sorted({info[4][0] for info in infos})
        except (OSError, ValueError):
            return "", []
    if not addresses or any(_is_blocked_address(addr, allow_private_lan) for addr in addresses):
        return "", []
    return clean, addresses


def normalize_dashboard_pages(cfg: dict) -> List[Dict[str, Any]]:
    """
    Ensures `dashboard.pages` is always a non-empty list of `{id, title, template, slots}`.
    If only legacy `dashboard.template` / `dashboard.slots` exist, migrates them to `pages[0]`.
    """
    dash = cfg.get("dashboard", {})
    pages = dash.get("pages")
    if isinstance(pages, list) and len(pages) > 0:
        normalized = []
        for idx, p in enumerate(pages):
            normalized.append({
                "id": p.get("id") or f"page_{idx + 1}",
                "title": p.get("title") or f"第 {idx + 1} 页",
                "template": p.get("template") or "2_1",
                "slots": dict(p.get("slots") or {"top_left": "calendar", "bottom_left": "weather", "right": "todo"})
            })
        return normalized

    tpl = dash.get("template", "2_1")
    slots = dash.get("slots", {"top_left": "calendar", "bottom_left": "weather", "right": "todo"})
    return [
        {
            "id": "page_1",
            "title": "第 1 页 · 主看板",
            "template": tpl,
            "slots": dict(slots)
        }
    ]


def load_config() -> dict:
    """读取 config.json 并与默认值合并。文件缺失时回退 config.example.json 或默认配置。"""
    cfg = dict(DEFAULT_CONFIG)
    source_path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else (
        EXAMPLE_CONFIG_PATH if os.path.exists(EXAMPLE_CONFIG_PATH) else None
    )
    if source_path:
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                cfg = _merge(DEFAULT_CONFIG, json.load(f))
        except Exception as e:
            print(f"[Config Warning] 读取配置文件失败: {e}，使用默认配置")
    cfg.setdefault("dashboard", {})["pages"] = normalize_dashboard_pages(cfg)
    return cfg


_CONFIG_LOCK = threading.RLock()


@contextmanager
def config_transaction():
    """串行化跨 config.json 与 .env 的复合写入事务。"""
    with _CONFIG_LOCK:
        yield


def _atomic_write_text(path: str, content: str):
    """同目录写入后原子替换，避免并发读取到半截配置或凭据文件。"""
    tmp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def save_config(updates: dict) -> dict:
    """将更新项合并写入 config.json 并返回最新配置（递归剥离任何明文密钥）。"""
    with _CONFIG_LOCK:
        current = load_config()
        merged = _merge(current, updates)
        if "dashboard" in merged:
            pages = normalize_dashboard_pages(merged)
            merged["dashboard"]["pages"] = pages
            merged["dashboard"]["template"] = pages[0]["template"]
            merged["dashboard"]["slots"] = pages[0]["slots"]
        merged = _strip_plaintext_secrets(merged)
        _atomic_write_text(CONFIG_PATH, json.dumps(merged, ensure_ascii=False, indent=2))
        return merged


def get_secret(section: dict, key: str = "token") -> str:
    """仅从 `{key}_env` 指定的环境变量读取凭据，不回退到明文配置。"""
    env_name = section.get(f"{key}_env")
    return os.environ.get(env_name, "") if env_name else ""


def save_env_secret(key: str, value: str) -> bool:
    """原子保存单个环境变量凭据；拒绝非法键名和会注入额外行的值。"""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key or "") or value is None:
        return False
    if "\n" in value or "\r" in value:
        return False
    with _CONFIG_LOCK:
        lines = []
        found = False
        if os.path.exists(ENV_PATH):
            try:
                with open(ENV_PATH, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except OSError:
                lines = []
        new_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"export {key}="):
                new_lines.append(f"{key}={value}\n")
                found = True
            else:
                new_lines.append(line)
        if not found:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f"{key}={value}\n")
        try:
            _atomic_write_text(ENV_PATH, "".join(new_lines))
            os.environ[key] = value
            return True
        except OSError as e:
            print(f"[Config Warning] 保存 .env 密钥失败: {e}")
            return False
