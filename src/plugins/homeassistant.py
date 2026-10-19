"""
Home Assistant Integration Module (v1.0).
Fetches indoor environment sensor metrics (temperature, humidity) from Home Assistant REST API.
"""

import json
import urllib.request
import ssl
from typing import Optional, Any


class HomeAssistantClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.ctx = ssl._create_unverified_context()
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "OpenInk-N516/1.0"
        }

    def _api_get(self, endpoint: str) -> Optional[Any]:
        if not self.base_url or not self.token:
            return None
        url = f"{self.base_url}/api/{endpoint.lstrip('/')}"
        req = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=6) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        return None

    def get_sensors_data(self, sensor_configs: list) -> list:
        """批量获取室内环境传感器状态"""
        results = []
        for item in sensor_configs:
            sid = item.get("id")
            sname = item.get("name", sid)
            data = self._api_get(f"states/{sid}")
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
