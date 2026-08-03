#!/usr/bin/env python3
"""Stáhne předpověď počasí a kvalitu ovzduší pro Hradec Králové.

Zdrojem je Open-Meteo (https://open-meteo.com) — bez API klíče, zdarma pro
nekomerční použití. Výstupem je JSON s denní předpovědí na 5 dní a dnešní
kvalitou ovzduší, ze kterého agent píše pole `weather` v digestu.

Agent z výstupu NIC nedopočítává ani nedomýšlí — bere jen hodnoty, které
tu jsou (Železné pravidlo platí i pro počasí).

Používá pouze standardní knihovnu.

Použití:
    python3 scripts/fetch_weather.py                      # -> stdout
    python3 scripts/fetch_weather.py --out /tmp/weather.json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

PLACE = "Hradec Králové"
LATITUDE = 50.2092
LONGITUDE = 15.8328
TIMEZONE = "Europe/Prague"
FORECAST_DAYS = 5
TIMEOUT = 20

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

WEEKDAYS = [
    "pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle",
]

# WMO weather interpretation codes -> česky.
WMO_CODES = {
    0: "jasno",
    1: "skoro jasno",
    2: "polojasno",
    3: "zataženo",
    45: "mlha",
    48: "mlha s námrazou",
    51: "slabé mrholení",
    53: "mrholení",
    55: "husté mrholení",
    56: "mrznoucí mrholení",
    57: "silné mrznoucí mrholení",
    61: "slabý déšť",
    63: "déšť",
    65: "silný déšť",
    66: "mrznoucí déšť",
    67: "silný mrznoucí déšť",
    71: "slabé sněžení",
    73: "sněžení",
    75: "silné sněžení",
    77: "sněhová zrna",
    80: "slabé přeháňky",
    81: "přeháňky",
    82: "silné přeháňky",
    85: "slabé sněhové přeháňky",
    86: "silné sněhové přeháňky",
    95: "bouřky",
    96: "bouřky s kroupami",
    99: "silné bouřky s kroupami",
}

# WMO kód -> název ikony, kterou umí vykreslit build_site.py.
def icon_for_code(code: int) -> str:
    if code == 0:
        return "clear"
    if code in (1, 2):
        return "partly"
    if code == 3:
        return "cloudy"
    if code in (45, 48):
        return "fog"
    if 51 <= code <= 67 or 80 <= code <= 82:
        return "rain"
    if 71 <= code <= 77 or code in (85, 86):
        return "snow"
    if code >= 95:
        return "storm"
    return "cloudy"


# Evropský index kvality ovzduší (EAQI) -> slovní hodnocení.
EAQI_LEVELS = [
    (20, "dobrá"),
    (40, "přijatelná"),
    (60, "zhoršená"),
    (80, "špatná"),
    (100, "velmi špatná"),
]


def fetch_json(base: str, params: dict) -> dict:
    url = f"{base}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "news-digest"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.load(resp)


def eaqi_label(value: float) -> str:
    for limit, label in EAQI_LEVELS:
        if value <= limit:
            return label
    return "extrémně špatná"


def build_days(daily: dict) -> list[dict]:
    days = []
    for i, iso in enumerate(daily["time"]):
        d = date.fromisoformat(iso)
        code = int(daily["weather_code"][i])
        days.append(
            {
                "date": iso,
                "weekday": WEEKDAYS[d.weekday()],
                "is_today": i == 0,
                "description": WMO_CODES.get(code, f"kód {code}"),
                "icon": icon_for_code(code),
                "temp_min_c": daily["temperature_2m_min"][i],
                "temp_max_c": daily["temperature_2m_max"][i],
                "precipitation_mm": daily["precipitation_sum"][i],
                "precipitation_probability_pct":
                    daily["precipitation_probability_max"][i],
                "wind_gusts_kmh": daily["wind_gusts_10m_max"][i],
            }
        )
    return days


def build_air_quality(hourly: dict) -> dict | None:
    values = [v for v in hourly.get("european_aqi") or [] if v is not None]
    if not values:
        return None
    worst = max(values)
    return {
        "european_aqi_today_max": worst,
        "label": eaqi_label(worst),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, help="kam zapsat JSON (default stdout)")
    args = ap.parse_args()

    try:
        forecast = fetch_json(
            FORECAST_URL,
            {
                "latitude": LATITUDE,
                "longitude": LONGITUDE,
                "daily": ",".join(
                    [
                        "weather_code",
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_sum",
                        "precipitation_probability_max",
                        "wind_gusts_10m_max",
                    ]
                ),
                "timezone": TIMEZONE,
                "forecast_days": FORECAST_DAYS,
            },
        )
    except OSError as exc:
        print(f"CHYBA: předpověď se nepodařilo stáhnout — {exc}",
              file=sys.stderr)
        return 1

    # Kvalita ovzduší je bonus — když selže, počasí se pošle bez ní.
    air = None
    try:
        air_raw = fetch_json(
            AIR_URL,
            {
                "latitude": LATITUDE,
                "longitude": LONGITUDE,
                "hourly": "european_aqi",
                "timezone": TIMEZONE,
                "forecast_days": 1,
            },
        )
        air = build_air_quality(air_raw.get("hourly") or {})
    except OSError as exc:
        print(f"varování: kvalita ovzduší nedostupná — {exc}", file=sys.stderr)

    payload = {
        "place": PLACE,
        "source": "open-meteo.com",
        "days": build_days(forecast["daily"]),
        "air_quality": air,
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"zapsáno: {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
