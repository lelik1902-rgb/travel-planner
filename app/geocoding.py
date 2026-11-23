"""Пошук міста через OpenStreetMap Nominatim API."""

import httpx

from .models import City, Stop

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim вимагає змістовний User-Agent для кожного запиту.
USER_AGENT = "tk42-travel-planner/1.0 (student lab project)"
# Запас навколо меж міста (у градусах), щоб не відкидати передмістя.
BBOX_MARGIN = 0.15


class CityNotFound(Exception):
    pass


class GeocodingError(Exception):
    pass


async def geocode_city(name: str) -> City:
    """Повертає офіційну назву, центр і межі міста."""
    params = {"q": name, "format": "jsonv2", "limit": 1, "accept-language": "uk"}
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(NOMINATIM_URL, params=params)
            response.raise_for_status()
            results = response.json()
    except httpx.HTTPError as error:
        raise GeocodingError(f"OpenStreetMap недоступний: {error}") from error

    if not results:
        raise CityNotFound(name)
    place = results[0]
    south, north, west, east = (float(v) for v in place["boundingbox"])
    return City(
        name=place.get("name") or name,
        display_name=place["display_name"],
        lat=float(place["lat"]),
        lon=float(place["lon"]),
        bbox=(south, north, west, east),
    )


def inside_city(stop: Stop, city: City) -> bool:
    """Чи потрапляють координати від Gemini у межі міста (із запасом)."""
    south, north, west, east = city.bbox
    return (south - BBOX_MARGIN <= stop.lat <= north + BBOX_MARGIN
            and west - BBOX_MARGIN <= stop.lon <= east + BBOX_MARGIN)
