"""Formatters for weather data."""

from lafcbot.formatters.base import BaseFormatter


class WeatherFormatter(BaseFormatter):
    """Formats weather command responses."""

    def _format_aqi_category(self, aqi: int) -> str:
        """
        Get AQI category and emoji.

        Args:
            aqi: Air Quality Index value

        Returns:
            Category string with emoji
        """
        if aqi <= 50:
            return "Good 🟢"
        elif aqi <= 100:
            return "Moderate 🟡"
        elif aqi <= 150:
            return "Unhealthy for Sensitive Groups 🟠"
        elif aqi <= 200:
            return "Unhealthy 🔴"
        elif aqi <= 300:
            return "Very Unhealthy 🟣"
        else:
            return "Hazardous ⚫"

    async def format_weather_report(
        self,
        location: str,
        temperature_f: float,
        condition: str,
        humidity: int,
        wind_speed: float,
        aqi: int | None = None,
    ) -> str:
        """
        Format !weather command output with AQI.

        Args:
            location: Location name
            temperature_f: Temperature in Fahrenheit
            condition: Weather condition description
            humidity: Humidity percentage
            wind_speed: Wind speed in mph
            aqi: Air Quality Index (optional)

        Returns:
            Formatted weather report string
        """
        lines = [
            f"**Weather for {location}:**",
            f"🌡️ Temperature: {temperature_f:.1f}°F",
            f"☁️ Condition: {condition}",
            f"💧 Humidity: {humidity}%",
            f"💨 Wind Speed: {wind_speed:.1f} mph",
        ]

        if aqi is not None:
            aqi_category = self._format_aqi_category(aqi)
            lines.append(f"🌫️ Air Quality: {aqi} ({aqi_category})")

        return "\n".join(lines)
