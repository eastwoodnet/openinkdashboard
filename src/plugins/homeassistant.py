"""
Home Assistant Integration Module (v1.2).
Fetches indoor environment sensor metrics (temperature, humidity) from Home Assistant REST API.
"""

import json
import re
import urllib.request
import ssl
from typing import Optional, Any
from config import validate_external_url

_ENTITY_ID_RE = re.compile(r"^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$")
MAX_HA_RESP_BYTES = 256 * 1024


class HomeAssistantClient:
    def __init__(self, base_url: str, token: str):
        clean_base = validate_external_url(base_url, allow_private_lan=True)
        self.base_url = clean_base.rstrip("/") if clean_base else ""
        self.token = (token or "").strip()
        self.ctx = ssl._create_unverified_context()
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
                    return json.loads(resp.read(MAX_HA_RESP_BYTES).decode("utf-8"))
        except Exception:
            return None
        return None

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
                results.append({
                    "id": sid,
                    "name": sname,
                    "value": "--",
                    "unit": "",
                    "display": "--"
                })
        return results
