"""Тести API з підставними відповідями Gemini та OpenStreetMap (без мережі)."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import gemini_client, geocoding, main
from app.models import City, DayPlan, GeminiPlan, PlanRequest, Stop

LVIV = City(name="Львів", display_name="Львів, Україна", lat=49.84, lon=24.03,
            bbox=(49.77, 49.90, 23.92, 24.13))


def make_plan(days: int, far_away: bool = False) -> GeminiPlan:
    stop = Stop(time="10:00", name="Площа Ринок", description="Серце старого міста.",
                duration_min=60, lat=49.8419, lon=24.0315)
    far = Stop(time="13:00", name="Десь у Києві", description="Помилкова точка.",
               duration_min=30, lat=50.45, lon=30.52)
    return GeminiPlan(
        summary="Маршрут центром Львова.",
        days=[DayPlan(day=d, title=f"День {d}", stops=[stop] + ([far] if far_away else []))
              for d in range(1, days + 1)],
        tips=["Зручне взуття", "Готівка для кав'ярень"],
    )


@pytest.fixture
def client(monkeypatch):
    async def fake_geocode(name):
        if name.lower() == "атлантида":
            raise geocoding.CityNotFound(name)
        return LVIV

    async def fake_generate(request: PlanRequest, city: City):
        return make_plan(request.days, far_away=True), "test-model"

    monkeypatch.setattr(geocoding, "geocode_city", fake_geocode)
    monkeypatch.setattr(gemini_client, "generate_plan", fake_generate)
    return TestClient(main.app)


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Планувальник подорожей" in response.text


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_plan_success(client):
    response = client.post("/api/plan", json={"city": "Львів", "days": 2, "interests": ["кава"]})
    assert response.status_code == 200
    data = response.json()
    assert data["city"]["name"] == "Львів"
    assert len(data["days"]) == 2
    assert data["days"][0]["stops"][0]["verified"] is True


def test_point_outside_city_is_not_verified(client):
    data = client.post("/api/plan", json={"city": "Львів", "days": 1}).json()
    assert data["days"][0]["stops"][1]["verified"] is False


def test_city_not_found(client):
    response = client.post("/api/plan", json={"city": "Атлантида", "days": 1})
    assert response.status_code == 404


@pytest.mark.parametrize("payload", [
    {"city": "Львів", "days": 9},
    {"city": "Львів", "days": 0},
    {"city": " ", "days": 2},
    {"city": "Львів", "days": 2, "pace": "turbo"},
])
def test_invalid_input(client, payload):
    assert client.post("/api/plan", json=payload).status_code == 422


def test_gemini_error_returns_502(client, monkeypatch):
    async def broken(request, city):
        raise gemini_client.GeminiError("Помилка Gemini API: quota exceeded")

    monkeypatch.setattr(gemini_client, "generate_plan", broken)
    response = client.post("/api/plan", json={"city": "Львів", "days": 1})
    assert response.status_code == 502
    assert "Gemini" in response.json()["detail"]


def test_extra_days_from_gemini_are_trimmed(client, monkeypatch):
    async def too_many(request, city):
        return make_plan(request.days + 2), "test-model"

    monkeypatch.setattr(gemini_client, "generate_plan", too_many)
    data = client.post("/api/plan", json={"city": "Львів", "days": 2}).json()
    assert [d["day"] for d in data["days"]] == [1, 2]


def test_prompt_contains_user_preferences():
    request = PlanRequest(city="Львів", days=3, interests=["музеї"], pace="relaxed", budget="low")
    prompt = gemini_client.build_prompt(request, LVIV)
    assert "рівно 3 днів" in prompt and "музеї" in prompt and "економний" in prompt


class FakeModels:
    """Імітує client.aio.models: перша модель перевантажена, друга відповідає."""

    def __init__(self, failures):
        self.failures = failures
        self.calls = []

    async def generate_content(self, model, contents, config):
        self.calls.append(model)
        code = self.failures.get(model)
        if code:
            raise gemini_client.errors.APIError(code, {"error": {"message": "busy", "status": "X"}})
        return type("R", (), {"text": make_plan(1).model_dump_json()})()


def patch_client(monkeypatch, fake):
    client = type("C", (), {"aio": type("A", (), {"models": fake})()})()
    monkeypatch.setattr(gemini_client.genai, "Client", lambda api_key: client)
    async def no_wait(seconds):
        return None

    monkeypatch.setattr(gemini_client.asyncio, "sleep", no_wait)
    monkeypatch.setenv("GEMINI_API_KEY", "test")


def test_falls_back_to_next_model_on_503(monkeypatch):
    fake = FakeModels({gemini_client.MODELS[0]: 503})
    patch_client(monkeypatch, fake)
    plan, model = asyncio.run(gemini_client.generate_plan(PlanRequest(city="Львів", days=1), LVIV))
    assert model == gemini_client.MODELS[1]
    assert fake.calls == [gemini_client.MODELS[0]] * 2 + [gemini_client.MODELS[1]]


def test_all_models_busy_gives_friendly_error(monkeypatch):
    patch_client(monkeypatch, FakeModels({m: 503 for m in gemini_client.MODELS}))
    with pytest.raises(gemini_client.GeminiError, match="перевантажений"):
        asyncio.run(gemini_client.generate_plan(PlanRequest(city="Львів", days=1), LVIV))


def test_bad_key_is_not_retried(monkeypatch):
    fake = FakeModels({m: 403 for m in gemini_client.MODELS})
    patch_client(monkeypatch, fake)
    with pytest.raises(gemini_client.GeminiError, match="GEMINI_API_KEY"):
        asyncio.run(gemini_client.generate_plan(PlanRequest(city="Львів", days=1), LVIV))
    assert len(fake.calls) == 1


def test_geocoder_falls_back_to_photon(monkeypatch):
    import httpx
    geocoding._cache.clear()

    async def blocked(client, name):
        raise httpx.HTTPError("629 Unknown Error")

    async def photon(client, name):
        return LVIV

    monkeypatch.setattr(geocoding, "_nominatim", blocked)
    monkeypatch.setattr(geocoding, "_photon", photon)
    assert asyncio.run(geocoding.geocode_city("Львів")) == LVIV


def test_geocoder_both_down_gives_friendly_error(monkeypatch):
    import httpx
    geocoding._cache.clear()

    async def blocked(client, name):
        raise httpx.HTTPError("down")

    monkeypatch.setattr(geocoding, "_nominatim", blocked)
    monkeypatch.setattr(geocoding, "_photon", blocked)
    with pytest.raises(geocoding.GeocodingError, match="тимчасово недоступний"):
        asyncio.run(geocoding.geocode_city("Львів"))


def test_geocoder_uses_cache(monkeypatch):
    geocoding._cache.clear()
    calls = []

    async def nominatim(client, name):
        calls.append(name)
        return LVIV

    monkeypatch.setattr(geocoding, "_nominatim", nominatim)
    asyncio.run(geocoding.geocode_city("Львів"))
    asyncio.run(geocoding.geocode_city(" львів "))
    assert calls == ["Львів"]
