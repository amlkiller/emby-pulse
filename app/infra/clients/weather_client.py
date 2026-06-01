import urllib.parse

import requests


class WeatherClient:
    @staticmethod
    def _headers() -> dict:
        return {"User-Agent": "Mozilla/5.0 (EmbyPulse)"}

    def get_qweather_location(self, host: str, city: str, api_key: str, *, timeout: float = 6):
        encoded_city = urllib.parse.quote(city)
        return requests.get(
            f"https://{host}/geo/v2/city/lookup?location={encoded_city}",
            headers={**self._headers(), "X-QW-Api-Key": api_key},
            timeout=timeout,
        )

    def get_qweather_now(self, host: str, location_id: str, api_key: str, *, timeout: float = 6):
        return requests.get(
            f"https://{host}/v7/weather/now?location={location_id}",
            headers={**self._headers(), "X-QW-Api-Key": api_key},
            timeout=timeout,
        )

    def get_amap_weather(self, city: str, api_key: str, *, timeout: float = 6):
        encoded_city = urllib.parse.quote(city)
        return requests.get(
            f"https://restapi.amap.com/v3/weather/weatherInfo?city={encoded_city}&key={api_key}&extensions=base",
            headers=self._headers(),
            timeout=timeout,
        )

    def get_wttr_weather(self, city: str, *, proxies=None, timeout: float = 6):
        encoded_city = urllib.parse.quote(city)
        return requests.get(
            f"https://wttr.in/{encoded_city}?format=j1&lang=zh",
            proxies=proxies,
            headers=self._headers(),
            timeout=timeout,
        )


weather_client = WeatherClient()
