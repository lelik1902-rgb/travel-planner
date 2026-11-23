"""FastAPI-застосунок «Планувальник подорожей»: Gemini API + OpenStreetMap."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import gemini_client, geocoding
from .models import CheckedDay, CheckedStop, PlanRequest, PlanResponse

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Планувальник подорожей", version="1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "model": gemini_client.MODEL}


@app.post("/api/plan", response_model=PlanResponse)
async def create_plan(request: PlanRequest) -> PlanResponse:
    # 1. Знаходимо місто в OpenStreetMap: перевіряємо, що воно існує, ще до виклику Gemini.
    try:
        city = await geocoding.geocode_city(request.city)
    except geocoding.CityNotFound:
        raise HTTPException(404, f"Місто «{request.city}» не знайдено в OpenStreetMap.")
    except geocoding.GeocodingError as error:
        raise HTTPException(502, str(error))

    # 2. Gemini складає маршрут у форматі JSON за нашою схемою.
    try:
        plan, model = await gemini_client.generate_plan(request, city)
    except gemini_client.GeminiError as error:
        raise HTTPException(502, str(error))

    # 3. Перевіряємо координати від Gemini межами міста з OpenStreetMap.
    days = [
        CheckedDay(
            day=day.day,
            title=day.title,
            stops=[CheckedStop(**stop.model_dump(), verified=geocoding.inside_city(stop, city))
                   for stop in day.stops],
        )
        for day in sorted(plan.days, key=lambda d: d.day)[: request.days]
    ]
    if not days:
        raise HTTPException(502, "Gemini не повернув жодного дня маршруту.")

    return PlanResponse(city=city, summary=plan.summary, days=days,
                        tips=plan.tips[:5], model=model)
