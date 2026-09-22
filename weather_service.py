"""
Live Weather Telemetry Service
Wraps Open-Meteo Geocoding & Forecast APIs.
"""

from typing import Dict, Any, Optional, Tuple
import requests
import logging

from config import (
    OPEN_METEO_GEOCODING_URL,
    OPEN_METEO_FORECAST_URL,
    FORECAST_CURRENT_FIELDS,
    DEFAULT_TIMEOUT_SECONDS,
    WMO_WEATHER_CODES,
)

logger = logging.getLogger("weather_service")


class WeatherServiceError(Exception):
    """Base exception for weather retrieval failures."""
    pass


class LocationNotFoundError(WeatherServiceError):
    """Raised when a city or location name cannot be geocoded."""
    pass


class WeatherApiUnavailableError(WeatherServiceError):
    """Raised when the Open-Meteo endpoint fails, times out, or returns a 5xx."""
    pass


class WeatherService:
    def __init__(self, timeout: int = DEFAULT_TIMEOUT_SECONDS):
        self.timeout = timeout
        self.session = requests.Session()
        # Clean user-agent header per API etiquette
        self.session.headers.update({
            "User-Agent": "MediBuddyWeatherAdvisoryBot/1.0"
        })

    def geocode_city(self, city_name: str) -> Dict[str, Any]:
        """
        Resolves a freeform city name into geographic coordinates.
        Takes the primary candidate returned by Open-Meteo.
        """
        clean_name = city_name.strip()
        if not clean_name:
            raise LocationNotFoundError("No city name was provided to resolve.")

        params = {
            "name": clean_name,
            "count": 5,
            "language": "en",
            "format": "json",
        }

        try:
            resp = self.session.get(
                OPEN_METEO_GEOCODING_URL,
                params=params,
                timeout=self.timeout,
            )
        except (requests.RequestException, TimeoutError) as exc:
            logger.error(f"Geocoding network error for '{city_name}': {exc}")
            raise WeatherApiUnavailableError(f"Network error communicating with geocoding service: {exc}")

        if resp.status_code != 200:
            logger.error(f"Geocoding API responded with HTTP {resp.status_code}")
            raise WeatherApiUnavailableError(f"Geocoding service returned HTTP {resp.status_code}")

        data = resp.json()
        results = data.get("results")
        if not results or len(results) == 0:
            raise LocationNotFoundError(f"Could not resolve any geographic location for '{city_name}'.")

        # Select the primary result
        primary = results[0]
        return {
            "name": primary.get("name"),
            "latitude": float(primary.get("latitude")),
            "longitude": float(primary.get("longitude")),
            "country": primary.get("country", ""),
            "region": primary.get("admin1", ""),
            "timezone": primary.get("timezone", "UTC"),
        }

    def fetch_current_weather(
        self,
        latitude: float,
        longitude: float,
        simulate_failure: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetches live weather metrics from Open-Meteo for given coordinates.
        Explicitly requests all required telemetry fields.
        """
        if simulate_failure:
            raise WeatherApiUnavailableError("Simulated weather service downtime for verification.")

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(FORECAST_CURRENT_FIELDS),
        }

        try:
            resp = self.session.get(
                OPEN_METEO_FORECAST_URL,
                params=params,
                timeout=self.timeout,
            )
        except (requests.RequestException, TimeoutError) as exc:
            logger.error(f"Forecast API network error at ({latitude}, {longitude}): {exc}")
            raise WeatherApiUnavailableError(f"Network error contacting Open-Meteo forecast API: {exc}")

        if resp.status_code != 200:
            logger.error(f"Forecast API responded with HTTP {resp.status_code}")
            raise WeatherApiUnavailableError(f"Forecast API returned HTTP {resp.status_code}")

        payload = resp.json()
        current = payload.get("current")
        if not current:
            raise WeatherApiUnavailableError("Forecast API response lacked 'current' weather block.")

        weather_code = current.get("weather_code", 0)
        weather_desc = WMO_WEATHER_CODES.get(weather_code, "Unknown conditions")

        # Standardize and validate numeric values
        telemetry = {
            "timestamp": current.get("time"),
            "temperature_2m": float(current.get("temperature_2m", 0.0)),
            "relative_humidity_2m": float(current.get("relative_humidity_2m", 0.0)),
            "apparent_temperature": float(current.get("apparent_temperature", 0.0)),
            "precipitation": float(current.get("precipitation", 0.0)),
            "rain": float(current.get("rain", 0.0)),
            "weather_code": int(weather_code),
            "weather_description": weather_desc,
            "cloud_cover": float(current.get("cloud_cover", 0.0)),
            "wind_speed_10m": float(current.get("wind_speed_10m", 0.0)),
            "wind_gusts_10m": float(current.get("wind_gusts_10m", 0.0)),
            "uv_index": float(current.get("uv_index", 0.0)),
            "latitude": latitude,
            "longitude": longitude,
        }

        return telemetry

    def get_weather_for_city(
        self,
        city_name: str,
        simulate_failure: bool = False,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Convenience pipeline: resolves city, then pulls current weather.
        Returns: (location_meta, weather_telemetry)
        """
        loc = self.geocode_city(city_name)
        weather = self.fetch_current_weather(
            latitude=loc["latitude"],
            longitude=loc["longitude"],
            simulate_failure=simulate_failure,
        )
        weather["city_display"] = f"{loc['name']}, {loc['region']}, {loc['country']}".strip(", ")
        return loc, weather
