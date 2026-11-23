"""Пошук міста через OpenStreetMap: Nominatim, а якщо він недоступний — Photon."""

import logging

import httpx

from .models import City, Stop

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Photon (komoot) — запасний геокодер на тих самих даних OpenStreetMap.
PHOTON_URL = "https://photon.komoot.io/api/"
# Nominatim вимагає змістовний User-Agent для кожного запиту.
USER_AGENT = "tk42-travel-planner/1.0 (student lab project)"
# Запас навколо меж міста (у градусах), щоб не відкидати передмістя.
BBOX_MARGIN = 0.15
# Якщо геокодер не дав меж міста, беремо квадрат ±0.2° навколо центру.
DEFAULT_HALF_SIZE = 0.2

log = logging.getLogger("travel-planner")
# Кеш: одне й те саме місто не шукаємо повторно.
_cache: dict[str, City] = {}


class CityNotFound(Exception):
    pass


class GeocodingError(Exception):
    pass


async def _nominatim(client: httpx.AsyncClient, name: str) -> City | None:
    params = {"q": name, "format": "jsonv2", "limit": 1, "accept-language": "uk"}
    response = await client.get(NOMINATIM_URL, params=params)
    response.raise_for_status()
    results = response.json()
    if not results:
        return None
    place = results[0]
    south, north, west, east = (float(v) for v in place["boundingbox"])
    return City(
        name=place.get("name") or name,
        display_name=place["display_name"],
        lat=float(place["lat"]),
        lon=float(place["lon"]),
        bbox=(south, north, west, east),
    )


async def _photon(client: httpx.AsyncClient, name: str) -> City | None:
    response = await client.get(PHOTON_URL, params={"q": name, "limit": 1})
    response.raise_for_status()
    features = response.json().get("features") or []
    if not features:
        return None
    props = features[0]["properties"]
    lon, lat = features[0]["geometry"]["coordinates"]
    extent = props.get("extent")  # [захід, північ, схід, південь]
    if extent and len(extent) == 4:
        west, north, east, south = (float(v) for v in extent)
    else:
        south, north = lat - DEFAULT_HALF_SIZE, lat + DEFAULT_HALF_SIZE
        west, east = lon - DEFAULT_HALF_SIZE, lon + DEFAULT_HALF_SIZE
    parts = [props.get("name"), props.get("state"), props.get("country")]
    return City(
        name=props.get("name") or name,
        display_name=", ".join(p for p in parts if p) or name,
        lat=float(lat),
        lon=float(lon),
        bbox=(south, north, west, east),
    )


async def geocode_city(name: str) -> City:
    """Повертає офіційну назву, центр і межі міста."""
    key = name.strip().lower()
    if key in _cache:
        return _cache[key]

    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": USER_AGENT}) as client:
        for source in (_nominatim, _photon):
            try:
                city = await source(client, name)
            except (httpx.HTTPError, KeyError, ValueError) as error:
                log.warning("Геокодер %s недоступний: %s", source.__name__, error)
                continue
            if city is None:
                raise CityNotFound(name)
            _cache[key] = city
            return city

    raise GeocodingError("Сервіс карт OpenStreetMap тимчасово недоступний. Спробуйте ще раз за хвилину.")


def inside_city(stop: Stop, city: City) -> bool:
    """Чи потрапляють координати від Gemini у межі міста (із запасом)."""
    south, north, west, east = city.bbox
    return (south - BBOX_MARGIN <= stop.lat <= north + BBOX_MARGIN
            and west - BBOX_MARGIN <= stop.lon <= east + BBOX_MARGIN)
