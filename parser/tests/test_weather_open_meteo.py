"""Тесты погодного парсера Open-Meteo (parse/accumulate — офлайн на фикстуре)."""
import json
from pathlib import Path

from egrn_parser.parsers import weather_open_meteo as W

FIX = Path(__file__).parent / "fixtures" / "weather" / "open_meteo_archive_sample.json"
PAYLOAD = json.loads(FIX.read_text(encoding="utf-8"))


def test_build_archive_url():
    url = W.build_archive_url(45.04, 38.97, "2024-07-01", "2024-07-03")
    assert url.startswith("https://archive-api.open-meteo.com/v1/archive?")
    assert "latitude=45.04" in url and "longitude=38.97" in url
    assert "shortwave_radiation_sum" in url and "windgusts_10m_max" in url


def test_parse_daily():
    days = W.parse_daily(PAYLOAD)
    assert len(days) == 3
    d0 = days[0]
    assert d0["date"] == "2024-07-01"
    assert d0["temp_max"] == 30.5 and d0["temp_mean"] == 24.0
    assert d0["precip_mm"] == 0.0 and d0["radiation_mj"] == 28.3
    assert d0["wind_max"] == 15.2 and d0["gust_max"] == 28.0


def test_accumulate():
    acc = W.accumulate(W.parse_daily(PAYLOAD))
    assert acc["n_days"] == 3
    # GDD база 10: (24-10)+(25.5-10)+(22.4-10) = 14+15.5+12.4 = 41.9
    assert acc["gdd"] == 41.9
    assert acc["precip_mm"] == 17.5             # 0+5.4+12.1
    assert acc["radiation_mj"] == 74.1          # 28.3+26.0+19.8
    assert acc["wind_max"] == 22.0              # max
    assert acc["gust_max"] == 41.5
    assert acc["temp_mean_avg"] == 23.97


def test_accumulate_uses_minmax_when_mean_absent():
    days = [{"temp_max": 30.0, "temp_min": 10.0, "precip_mm": 1.0}]  # mean отсутствует
    acc = W.accumulate(days)
    assert acc["gdd"] == 10.0                   # mean=(30+10)/2=20 → 20-10
    assert acc["precip_mm"] == 1.0


def test_accumulate_empty():
    acc = W.accumulate([])
    assert acc["n_days"] == 0 and acc["gdd"] == 0.0 and acc["temp_mean_avg"] is None
