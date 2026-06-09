"""
egrn_parser/parsers/weather_open_meteo.py — накопленная погода по геоточке
(бесплатный Open-Meteo Archive API, без ключа). ADR-006 §J: «накопленные погодные
условия с момента посадки» — ценообразующий признак насаждения на контуре ЗУ.

Источник: https://archive-api.open-meteo.com/v1/archive (исторические daily-данные).
За день: температура (max/min/mean), осадки, суммарная радиация, ветер, порывы.

Разделение: `build_archive_url`/`fetch_archive` (сеть) ↔ `parse_daily`/`accumulate`
(чистые, тестируются на сохранённом JSON без сети). `accumulated_since_planting` —
агрегат с {год посадки}-01-01 по сегодня (GDD база 10°C для винограда).
"""
from __future__ import annotations

import datetime as _dt
import json
import urllib.parse
import urllib.request
from typing import Any, Optional

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Запрашиваемые daily-переменные Open-Meteo → наши ключи.
_FIELD_MAP = {
    "temp_max": "temperature_2m_max",
    "temp_min": "temperature_2m_min",
    "temp_mean": "temperature_2m_mean",
    "precip_mm": "precipitation_sum",
    "radiation_mj": "shortwave_radiation_sum",
    "wind_max": "windspeed_10m_max",
    "gust_max": "windgusts_10m_max",
}
DAILY_VARS = list(_FIELD_MAP.values())

VINE_BASE_TEMP_C = 10.0          # биологический ноль винограда (GDD база)


def build_archive_url(lat: float, lon: float, start: str, end: str, *,
                      timezone: str = "auto") -> str:
    """URL Open-Meteo Archive для геоточки и периода [start, end] (YYYY-MM-DD)."""
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "start_date": start, "end_date": end,
        "daily": ",".join(DAILY_VARS), "timezone": timezone})
    return f"{ARCHIVE_URL}?{q}"


def fetch_archive(lat: float, lon: float, start: str, end: str, *,
                  timeout: int = 30) -> dict[str, Any]:
    """GET Open-Meteo Archive → JSON. Требует исходящей сети (может быть закрыта)."""
    url = build_archive_url(lat, lon, start, end)
    with urllib.request.urlopen(url, timeout=timeout) as resp:   # noqa: S310 (доверенный хост)
        return json.loads(resp.read().decode("utf-8"))


def parse_daily(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Ответ Open-Meteo → список по дням {date, temp_max/min/mean, precip_mm,
    radiation_mj, wind_max, gust_max}."""
    daily = (payload or {}).get("daily") or {}
    times = daily.get("time") or []
    out = []
    for i, date in enumerate(times):
        row: dict[str, Any] = {"date": date}
        for key, src in _FIELD_MAP.items():
            arr = daily.get(src) or []
            row[key] = arr[i] if i < len(arr) else None
        out.append(row)
    return out


def accumulate(days: list[dict[str, Any]], *,
               base_temp: float = VINE_BASE_TEMP_C) -> dict[str, Any]:
    """Накопленные показатели за период: GDD (Σ max(t_mean−base,0)), Σ осадки,
    Σ радиация, max ветер/порывы, средняя t, число дней."""
    acc = {"n_days": 0, "gdd": 0.0, "precip_mm": 0.0, "radiation_mj": 0.0,
           "wind_max": 0.0, "gust_max": 0.0, "temp_mean_avg": None}
    means = []
    for r in days:
        acc["n_days"] += 1
        tm = r.get("temp_mean")
        if tm is None and r.get("temp_max") is not None and r.get("temp_min") is not None:
            tm = (r["temp_max"] + r["temp_min"]) / 2.0
        if tm is not None:
            means.append(tm)
            acc["gdd"] += max(tm - base_temp, 0.0)
        for k in ("precip_mm", "radiation_mj"):
            if r.get(k) is not None:
                acc[k] += r[k]
        for k in ("wind_max", "gust_max"):
            if r.get(k) is not None:
                acc[k] = max(acc[k], r[k])
    if means:
        acc["temp_mean_avg"] = round(sum(means) / len(means), 2)
    acc["gdd"] = round(acc["gdd"], 1)
    acc["precip_mm"] = round(acc["precip_mm"], 1)
    acc["radiation_mj"] = round(acc["radiation_mj"], 1)
    return acc


def accumulated_since_planting(lat: float, lon: float, planting_year: int, *,
                               end: Optional[str] = None,
                               base_temp: float = VINE_BASE_TEMP_C) -> dict[str, Any]:
    """Накопленная погода с {planting_year}-01-01 по `end` (по умолч. сегодня).

    Делает сетевой запрос (Open-Meteo). Для офлайн-тестов используйте
    parse_daily+accumulate на сохранённом JSON."""
    start = f"{planting_year}-01-01"
    end = end or _dt.date.today().isoformat()
    payload = fetch_archive(lat, lon, start, end)
    out = accumulate(parse_daily(payload), base_temp=base_temp)
    out.update({"lat": lat, "lon": lon, "start": start, "end": end})
    return out
