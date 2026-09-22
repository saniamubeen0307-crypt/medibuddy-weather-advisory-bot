"""
Configuration and Environment Settings
Weather-Advisory Support Bot
"""

from pathlib import Path
import os

# Base Directories
BASE_DIR = Path(__file__).resolve().parent
SOPS_FILE_PATH = BASE_DIR / "sops.yaml"
STATIC_DIR = BASE_DIR / "static"

# Server Settings
SERVER_HOST = os.getenv("HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("PORT", "8000"))

# Open-Meteo Endpoints (Free, No API key required)
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_TIMEOUT_SECONDS = 8

# Requested Weather Telemetry Fields
# Note: Explicit listing is required by Open-Meteo; otherwise metadata is returned without values.
FORECAST_CURRENT_FIELDS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "precipitation",
    "rain",
    "weather_code",
    "cloud_cover",
    "wind_speed_10m",
    "wind_gusts_10m",
    "uv_index",
]

# LLM / Synthesizer Settings
# Supported providers: 'openai', 'gemini', 'anthropic', or 'template_fallback'
# If no external API key is provided, system falls back to strict template synthesis
# to guarantee 100% operational functionality and policy adherence during tests.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# WMO Weather Code Descriptions for Human-Readable Reporting
WMO_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}
