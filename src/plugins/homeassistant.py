"""
Home Assistant Integration Module (v1.2).
Fetches indoor environment sensor metrics (temperature, humidity) from Home Assistant REST API.
"""

import json
import os
import re
import urllib.request
import ssl
from typing import Optional, Any
from config import validate_external_url

_ENTITY_ID_RE = re.compile(r"^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$")
MAX_HA_RESP_BYTES = 256 * 1024


class HomeAssistantClient:
    def __init__(self, base_url: str, token: str, ca_file: str = ""):
        clean_base = validate_external_url(base_url, allow_private_lan=True)
        self.base_url = clean_base.rstrip("/") if clean_base else ""
        self.token = (token or "").strip()
        # 自签名内网 HA 通过显式 CA 文件信任，禁止关闭证书和主机名验证。
        self.ctx = ssl.create_default_context(cafile=ca_file or os.environ.get("HA_CA_FILE") or None)
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "OpenInk-N516/1.2"
        }

    def _api_get(self, endpoint: str) -> Optional[Any]:
        if not self.base_url or not self.token:
            return None
        url = f"{self.base_url}/api/{endpoint.lstrip('/')}"
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=4) as resp:
                if resp.status == 200:
                    body = resp.read(MAX_HA_RESP_BYTES + 1)
                    if len(body) > MAX_HA_RESP_BYTES:
                        raise ValueError("HA response too large")
                    return json.loads(body.decode("utf-8"))
        except Exception:
            return None
        return None

    def test_connection(self) -> dict:
        """测试 Home Assistant 实例与 Token 连通性并获取版本"""
        if not self.base_url:
            return {"ok": False, "error": "未提供 Home Assistant 实例地址 (URL)"}
        if not self.token:
            return {"ok": False, "error": "未提供长期访问令牌 (Token)"}
        url = f"{self.base_url}/api/"
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=4) as resp:
                if resp.status == 200:
                    body = resp.read(MAX_HA_RESP_BYTES + 1)
                    if len(body) > MAX_HA_RESP_BYTES:
                        return {"ok": False, "error": "HA 响应超过大小限制"}
                    data = json.loads(body.decode("utf-8"))
                    version = ""
                    try:
                        cfg_data = self._api_get("config")
                        if cfg_data and isinstance(cfg_data, dict):
                            version = cfg_data.get("version", "")
                    except Exception:
                        pass
                    msg = "连接成功！HA API 正常运行" + (f" (版本: {version})" if version else "")
                    return {"ok": True, "version": version, "message": msg}
                return {"ok": False, "error": f"HTTP {resp.status} 响应异常"}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {"ok": False, "error": "401 鉴权失败：Token 无效或已过期"}
            return {"ok": False, "error": f"HTTP 错误 {e.code}: {e.reason}"}
        except Exception as e:
            return {"ok": False, "error": f"无法连通 HA 实例: {str(e)}"}

    def discover_sensors(self) -> list:
        """从 Home Assistant /api/states 获取所有传感器实体并按友好名称与类型排序"""
        states = self._api_get("states")
        if not states or not isinstance(states, list):
            return []
        sensors = []
        for entity in states:
            eid = entity.get("entity_id", "")
            if not eid.startswith("sensor."):
                continue
            attrs = entity.get("attributes", {})
            dev_class = attrs.get("device_class", "")
            unit = attrs.get("unit_of_measurement", "")
            fname = attrs.get("friendly_name") or eid
            state = entity.get("state", "--")
            sensors.append({
                "id": eid,
                "entity_id": eid,
                "friendly_name": fname,
                "state": state,
                "unit": unit,
                "device_class": dev_class,
                "display": f"{state} {unit}".strip() if unit else str(state)
            })

        def _sort_key(s):
            dc = s.get("device_class", "")
            if dc == "temperature":
                return (0, s["friendly_name"])
            if dc == "humidity":
                return (1, s["friendly_name"])
            if dc in ("battery", "power", "illuminance", "pressure", "energy"):
                return (2, s["friendly_name"])
            return (3, s["friendly_name"])

        sensors.sort(key=_sort_key)
        return sensors

    def get_sensors_data(self, sensor_configs: list) -> list:
        """批量获取室内环境传感器状态"""
        results = []
        for item in sensor_configs:
            sid = (item.get("id") or "").strip()
            sname = item.get("name", sid)
            data = self._api_get(f"states/{sid}") if _ENTITY_ID_RE.match(sid) else None
            if data:
                val = data.get("state", "--")
                unit = data.get("attributes", {}).get("unit_of_measurement", "")
                results.append({
                    "id": sid,
                    "name": sname,
                    "value": val,
                    "unit": unit,
                    "display": f"{val} {unit}".strip()
                })
            else:
                fallback_disp = item.get("display") or "--"
                results.append({
                    "id": sid,
                    "name": sname,
                    "value": "--",
                    "unit": "",
                    "display": fallback_disp
                })
        return results
