"""Open-Meteo API client for fetching current weather conditions."""

import asyncio
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class OpenMeteoError(Exception):
    """Base exception for Open-Meteo client errors."""


class OpenMeteoNetworkError(OpenMeteoError):
    """Network or timeout error while contacting Open-Meteo."""


class OpenMeteoTimeoutError(OpenMeteoNetworkError):
    """Timeout while contacting Open-Meteo."""


class WeatherData:
    """Weather data model."""

    def __init__(
        self,
        location: str,
        temperature_f: float,
        temperature_c: float,
        conditions: str,
        humidity: int,
        wind_speed_mph: float,
        wind_direction: int,
        feels_like_f: float,
        feels_like_c: float,
        temp_max_f: float,
        temp_min_f: float,
        precipitation_probability: int,
        air_quality_index: Optional[int] = None,
        air_quality_category: Optional[str] = None,
    ):
        self.location = location
        self.temperature_f = temperature_f
        self.temperature_c = temperature_c
        self.conditions = conditions
        self.humidity = humidity
        self.wind_speed_mph = wind_speed_mph
        self.wind_direction = wind_direction
        self.feels_like_f = feels_like_f
        self.feels_like_c = feels_like_c
        self.temp_max_f = temp_max_f
        self.temp_min_f = temp_min_f
        self.precipitation_probability = precipitation_probability
        self.air_quality_index = air_quality_index
        self.air_quality_category = air_quality_category

    def wind_direction_text(self) -> str:
        """Convert wind direction degrees to compass direction."""
        directions = [
            "N",
            "NNE",
            "NE",
            "ENE",
            "E",
            "ESE",
            "SE",
            "SSE",
            "S",
            "SSW",
            "SW",
            "WSW",
            "W",
            "WNW",
            "NW",
            "NNW",
        ]
        index = round(self.wind_direction / 22.5) % 16
        return directions[index]


class OpenMeteoClient:
    """Async client for fetching weather data from Open-Meteo."""

    WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
    AIR_QUALITY_API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
    GEOCODING_API_URL = "https://geocoding-api.open-meteo.com/v1/search"
    DEFAULT_TIMEOUT = 10

    # WMO Weather interpretation codes
    WEATHER_CODES = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        56: "Light freezing drizzle",
        57: "Dense freezing drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        66: "Light freezing rain",
        67: "Heavy freezing rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
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

    def __init__(self):
        """Initialize the Open-Meteo client."""
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def get_current_weather(self, location: str) -> Optional[WeatherData]:
        """
        Get current weather conditions for a location.

        Args:
            location: Location string (city name or ZIP code)

        Returns:
            WeatherData object or None if request failed
        """
        if not self._session:
            self._session = aiohttp.ClientSession()

        # Geocode the location first
        geocode_result = await self._geocode_location(location)
        if not geocode_result:
            logger.warning(f"Could not geocode location: {location}")
            return None

        lat, lon, display_name = geocode_result

        # Fetch weather data
        weather_params = {
            "latitude": lat,
            "longitude": lon,
            "current": [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "weather_code",
                "wind_speed_10m",
                "wind_direction_10m",
            ],
            "daily": [
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_probability_max",
            ],
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "auto",
            "forecast_days": 1,
        }

        # Fetch air quality data
        aqi_params = {
            "latitude": lat,
            "longitude": lon,
            "current": ["us_aqi"],
            "timezone": "auto",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.DEFAULT_TIMEOUT)

            weather_task = self._session.get(
                self.WEATHER_API_URL, params=weather_params, timeout=timeout
            )
            aqi_task = self._session.get(
                self.AIR_QUALITY_API_URL, params=aqi_params, timeout=timeout
            )

            async with weather_task as weather_response, aqi_task as aqi_response:
                if weather_response.status != 200:
                    logger.warning(
                        f"Weather request returned status {weather_response.status}"
                    )
                    return None

                weather_data = await weather_response.json()

                # Air quality is optional, don't fail if it's not available
                aqi_value = None
                if aqi_response.status == 200:
                    aqi_data = await aqi_response.json()
                    current_aqi = aqi_data.get("current", {})
                    aqi_value = current_aqi.get("us_aqi")

                return self._parse_weather_data(weather_data, display_name, aqi_value)

        except asyncio.TimeoutError as e:
            logger.error(f"Weather request timed out: {e}")
            raise OpenMeteoTimeoutError("Weather service request timed out") from e
        except aiohttp.ClientError as e:
            logger.error(f"Weather request failed: {e}")
            raise OpenMeteoNetworkError(
                "Network error contacting the weather service"
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error fetching weather: {e}")
            raise OpenMeteoError("Unexpected weather service error") from e

    # US state abbreviations map
    US_STATE_ABBR = {
        "AL": "Alabama",
        "AK": "Alaska",
        "AZ": "Arizona",
        "AR": "Arkansas",
        "CA": "California",
        "CO": "Colorado",
        "CT": "Connecticut",
        "DE": "Delaware",
        "FL": "Florida",
        "GA": "Georgia",
        "HI": "Hawaii",
        "ID": "Idaho",
        "IL": "Illinois",
        "IN": "Indiana",
        "IA": "Iowa",
        "KS": "Kansas",
        "KY": "Kentucky",
        "LA": "Louisiana",
        "ME": "Maine",
        "MD": "Maryland",
        "MA": "Massachusetts",
        "MI": "Michigan",
        "MN": "Minnesota",
        "MS": "Mississippi",
        "MO": "Missouri",
        "MT": "Montana",
        "NE": "Nebraska",
        "NV": "Nevada",
        "NH": "New Hampshire",
        "NJ": "New Jersey",
        "NM": "New Mexico",
        "NY": "New York",
        "NC": "North Carolina",
        "ND": "North Dakota",
        "OH": "Ohio",
        "OK": "Oklahoma",
        "OR": "Oregon",
        "PA": "Pennsylvania",
        "RI": "Rhode Island",
        "SC": "South Carolina",
        "SD": "South Dakota",
        "TN": "Tennessee",
        "TX": "Texas",
        "UT": "Utah",
        "VT": "Vermont",
        "VA": "Virginia",
        "WA": "Washington",
        "WV": "West Virginia",
        "WI": "Wisconsin",
        "WY": "Wyoming",
        "DC": "District of Columbia",
    }

    async def _geocode_location(
        self, location: str
    ) -> Optional[tuple[float, float, str]]:
        """
        Convert a location string to coordinates.

        Args:
            location: City name, ZIP code, or "City, State" format

        Returns:
            Tuple of (latitude, longitude, display_name) or None if failed
        """
        # Check if location has a state specified (e.g., "Pasadena, CA")
        state_filter = None
        if "," in location:
            parts = location.split(",")
            if len(parts) == 2:
                city_name = parts[0].strip()
                state_abbr = parts[1].strip().upper()

                # Convert abbreviation to full state name
                if state_abbr in self.US_STATE_ABBR:
                    state_filter = self.US_STATE_ABBR[state_abbr]
                    # Try with full query first (might help the API)
                    result = await self._geocode_query(
                        location, state_filter=state_filter
                    )
                    if result:
                        return result
                    # Then try just the city with state filter
                    result = await self._geocode_query(
                        city_name, state_filter=state_filter
                    )
                    if result:
                        return result

        # Try the original query first (for ZIP codes or simple city names)
        result = await self._geocode_query(location)
        if result:
            return result

        # If it fails and contains a comma, try just the city name
        if "," in location:
            city_only = location.split(",")[0].strip()
            result = await self._geocode_query(city_only)
            if result:
                return result

        return None

    async def _geocode_query(
        self, query: str, state_filter: str | None = None
    ) -> Optional[tuple[float, float, str]]:
        """Execute a single geocoding query.

        Args:
            query: Location query string
            state_filter: Optional state name to filter results
        """
        params = {
            "name": query,
            "count": 10,  # Get multiple results to find best match
            "language": "en",
            "format": "json",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=self.DEFAULT_TIMEOUT)
            async with self._session.get(
                self.GEOCODING_API_URL, params=params, timeout=timeout
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("results") and len(data["results"]) > 0:
                        # If state filter provided, prioritize results from that state
                        if state_filter:
                            for result in data["results"]:
                                if result.get("admin1") == state_filter:
                                    result = self._build_result(result)
                                    if result:
                                        return result

                        # Fall back to first result if no state match
                        result = self._build_result(data["results"][0])
                        if result:
                            return result
                return None
        except asyncio.TimeoutError as e:
            logger.error(f"Geocoding timed out: {e}")
            raise OpenMeteoTimeoutError("Geocoding request timed out") from e
        except aiohttp.ClientError as e:
            logger.error(f"Geocoding failed: {e}")
            raise OpenMeteoNetworkError("Geocoding network error") from e
        except Exception as e:
            logger.error(f"Geocoding failed: {e}")
            raise OpenMeteoError("Geocoding failed") from e

    def _build_result(self, result: dict) -> Optional[tuple[float, float, str]]:
        """Build result tuple from geocoding result dict."""
        lat = result.get("latitude")
        lon = result.get("longitude")
        name = result.get("name")
        country = result.get("country")
        admin1 = result.get("admin1")  # State/province

        if lat is not None and lon is not None:
            # Build display name
            display_parts = [name]
            if admin1:
                display_parts.append(admin1)
            if country:
                display_parts.append(country)
            display_name = ", ".join(display_parts)

            return (lat, lon, display_name)
        return None

    def _parse_weather_data(
        self, data: dict, display_name: str, aqi: Optional[int] = None
    ) -> Optional[WeatherData]:
        """Parse weather data from API response."""
        try:
            current = data.get("current")
            daily = data.get("daily")
            if not current:
                logger.warning("No current weather data in response")
                return None

            temp_f = current.get("temperature_2m")
            humidity = current.get("relative_humidity_2m")
            feels_like_f = current.get("apparent_temperature")
            wind_speed_mph = current.get("wind_speed_10m")
            wind_direction = current.get("wind_direction_10m")
            weather_code = current.get("weather_code")

            if temp_f is None:
                logger.warning("Missing temperature data")
                return None

            # Get daily forecast data
            temp_max_f = None
            temp_min_f = None
            precip_prob = 0
            if daily:
                temp_max_list = daily.get("temperature_2m_max")
                temp_min_list = daily.get("temperature_2m_min")
                precip_prob_list = daily.get("precipitation_probability_max")

                if temp_max_list and len(temp_max_list) > 0:
                    temp_max_f = temp_max_list[0]
                if temp_min_list and len(temp_min_list) > 0:
                    temp_min_f = temp_min_list[0]
                if precip_prob_list and len(precip_prob_list) > 0:
                    precip_prob = precip_prob_list[0]

            # Convert Fahrenheit to Celsius
            temp_c = (temp_f - 32) * 5 / 9
            feels_like_c = (
                (feels_like_f - 32) * 5 / 9 if feels_like_f is not None else temp_c
            )

            # Get weather condition description
            conditions = self.WEATHER_CODES.get(weather_code, "Unknown")

            # AQI category
            aqi_category = None
            if aqi is not None:
                if aqi <= 50:
                    aqi_category = "good"
                elif aqi <= 100:
                    aqi_category = "moderate"
                elif aqi <= 150:
                    aqi_category = "unhealthy for sensitive"
                elif aqi <= 200:
                    aqi_category = "unhealthy"
                elif aqi <= 300:
                    aqi_category = "very unhealthy"
                else:
                    aqi_category = "hazardous"

            return WeatherData(
                location=display_name,
                temperature_f=temp_f,
                temperature_c=temp_c,
                conditions=conditions,
                humidity=humidity or 0,
                wind_speed_mph=wind_speed_mph or 0,
                wind_direction=wind_direction or 0,
                feels_like_f=feels_like_f or temp_f,
                feels_like_c=feels_like_c,
                temp_max_f=temp_max_f or temp_f,
                temp_min_f=temp_min_f or temp_f,
                precipitation_probability=precip_prob or 0,
                air_quality_index=aqi,
                air_quality_category=aqi_category,
            )
        except Exception as e:
            logger.error(f"Failed to parse weather data: {e}")
            return None
