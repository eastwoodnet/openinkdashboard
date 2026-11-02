"""
Weather acquisition module.
Fetches real-time weather and three-day forecasts from wttr.in.
No API key required.
"""

import json
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List


def _translate_description(raw_desc: Any) -> str:
    raw = str(raw_desc or "天气不可用")
    trans_map = {
        "sunny": "晴天", "clear": "晴朗", "partly cloudy": "多云", "cloudy": "多云 / 阴",
        "overcast": "阴天", "mist": "薄雾", "fog": "大雾", "freezing fog": "冻雾",
        "patchy rain possible": "局部阵雨", "patchy light drizzle": "零星毛毛雨",
        "light drizzle": "毛毛细雨", "light rain": "小雨", "moderate rain": "中雨",
        "heavy rain": "大雨", "torrential rain": "大暴雨", "light snow": "小雪",
        "moderate snow": "中雪", "heavy snow": "大雪", "thundery outbreaks possible": "雷阵雨",
        "smoky haze": "阴霾 / 烟雾", "haze": "轻霾", "smoke": "烟霾", "dust": "浮尘", "sand": "扬沙"
    }
    raw_lower = raw.strip().lower()
    for eng, zh in trans_map.items():
        if eng in raw_lower:
            return zh
    return raw


def _condition_description(condition: Dict[str, Any]) -> str:
    lang_zh = condition.get("lang_zh-cn") or []
    weather_desc = condition.get("weatherDesc") or []
    if lang_zh:
        raw_desc = lang_zh[0].get("value")
    elif weather_desc:
        raw_desc = weather_desc[0].get("value")
    else:
        raw_desc = "天气不可用"
    return _translate_description(raw_desc)


def _build_forecast(weather_days: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    forecast = []
    labels = ("今天", "明天", "后天")
    for idx, day in enumerate(weather_days[:3]):
        hourly = day.get("hourly") or []
        if hourly:
            condition = min(
                hourly,
                key=lambda item: abs(int(item.get("time", 0) or 0) - 1200)
            )
        else:
            condition = {}

        raw_date = str(day.get("date", "--"))
        date_parts = raw_date.split("-")
        display_date = (
            f"{int(date_parts[1])}/{int(date_parts[2])}"
            if len(date_parts) == 3
            else raw_date
        )
        min_temp = day.get("mintempC", "--")
        max_temp = day.get("maxtempC", "--")
        forecast.append({
            "label": labels[idx],
            "date": display_date,
            "desc": _condition_description(condition),
            "range": f"{min_temp}°C ~ {max_temp}°C"
        })
    return forecast


def fetch_weather_wttr(city: str = "Beijing") -> dict:
    """从 wttr.in 获取实时天气及真实三日预报 (无需 API Key)"""
    url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1&lang=zh-cn"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "curl/7.68.0", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=4) as resp:
        data = json.loads(resp.read(512 * 1024).decode("utf-8"))

    current = (data.get("current_condition") or [{}])[0]
    weather_days = data.get("weather") or []
    today = weather_days[0] if weather_days else {}

    desc = _condition_description(current)
    temp_c = current.get("temp_C", "--")
    feels_c = current.get("FeelsLikeC", temp_c)
    humidity = current.get("humidity", "--")
    wind_dir_raw = current.get("winddir16Point", "").upper()
    wind_dir_map = {
        "N": "北风", "NNE": "东北风", "NE": "东北风", "ENE": "东偏北风",
        "E": "东风", "ESE": "东偏南风", "SE": "东南风", "SSE": "东南风",
        "S": "南风", "SSW": "西南风", "SW": "西南风", "WSW": "西偏南风",
        "W": "西风", "WNW": "西偏北风", "NW": "西北风", "NNW": "西北风"
    }
    wind_cn = wind_dir_map.get(wind_dir_raw, f"{wind_dir_raw}风" if wind_dir_raw else "--")
    wind_speed = current.get("windspeedKmph", "--")
    uv_index = current.get("uvIndex", "--")

    city_map = {
        "beijing": "北京", "shanghai": "上海", "shenzhen": "深圳",
        "guangzhou": "广州", "hangzhou": "杭州", "chengdu": "成都",
        "wuhan": "武汉", "nanjing": "南京", "tianjin": "天津",
        "chongqing": "重庆", "xian": "西安", "suzhou": "苏州"
    }
    display_city = city_map.get(city.strip().lower(), city)

    max_temp = today.get("maxtempC", "--")
    min_temp = today.get("mintempC", "--")

    return {
        "source": "wttr.in",
        "city": display_city,
        "desc": desc,
        "temp": f"{temp_c}°C",
        "temp_num": temp_c,
        "feels_like": f"{feels_c}°C",
        "temp_range": f"{min_temp}°C ~ {max_temp}°C",
        "humidity": f"{humidity}%",
        "wind": f"{wind_cn} {wind_speed}km/h",
        "wind_cn": wind_cn,
        "uv": uv_index,
        "forecast": _build_forecast(weather_days),
        "success": True
    }


def get_weather(city: str = "Beijing") -> dict:
    """获取天气信息，失败时保留明确的不可用状态。"""
    try:
        return fetch_weather_wttr(city)
    except Exception as e:
        print(f"[Warning] Failed to fetch weather for {city}: {e}")
        return {
            "source": "fallback",
            "city": city,
            "desc": "天气不可用",
            "temp": "--°C",
            "temp_num": "--",
            "feels_like": "--°C",
            "temp_range": "--°C ~ --°C",
            "humidity": "--%",
            "wind": "--",
            "wind_cn": "--",
            "uv": "--",
            "forecast": [],
            "success": False
        }


if __name__ == "__main__":
    w = get_weather("Beijing")
    print("Weather info:", w)
