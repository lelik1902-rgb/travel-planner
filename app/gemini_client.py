"""Генерація маршруту через Google Gemini API зі structured output (JSON-схема)."""

import asyncio
import logging
import os

from google import genai
from google.genai import errors
from pydantic import ValidationError

from .models import City, GeminiPlan, PlanRequest

# Основна модель і запасні: якщо одна перевантажена (503) або недоступна, пробуємо наступну.
MODELS = [m.strip() for m in os.getenv(
    "GEMINI_MODELS", "gemini-3.5-flash-lite,gemini-3.5-flash,gemini-2.5-flash").split(",") if m.strip()]
MODEL = MODELS[0]
ATTEMPTS_PER_MODEL = 2
RETRY_CODES = {429, 500, 502, 503, 504}   # тимчасові збої: повторюємо
SKIP_CODES = {404}                        # модель недоступна: одразу до наступної

log = logging.getLogger("travel-planner")

PACE = {"relaxed": "3 місця на день, без поспіху",
        "normal": "4 місця на день",
        "intense": "5 місць на день, насичено"}
BUDGET = {"low": "економний (безкоштовні місця, вулична їжа)",
          "medium": "середній",
          "high": "без обмежень (ресторани, платні екскурсії)"}


class GeminiError(Exception):
    pass


def build_prompt(request: PlanRequest, city: City) -> str:
    interests = ", ".join(request.interests) or "загальні враження від міста"
    return (
        f"Ти — досвідчений туристичний гід. Склади маршрут подорожі українською мовою.\n"
        f"Місто: {city.display_name} (центр: {city.lat:.4f}, {city.lon:.4f}).\n"
        f"Кількість днів: {request.days}. Темп: {PACE[request.pace]}.\n"
        f"Бюджет: {BUDGET[request.budget]}. Інтереси: {interests}.\n"
        "Вимоги:\n"
        f"- рівно {request.days} днів, поле day від 1 до {request.days};\n"
        "- лише реальні місця в цьому місті з точними координатами lat/lon;\n"
        "- місця одного дня розташовані поруч, у логічному порядку обходу;\n"
        "- час від 09:00 до 21:00, включи обід або вечерю в закладі;\n"
        "- не вигадуй ціни й години роботи."
    )


async def generate_plan(request: PlanRequest, city: City) -> tuple[GeminiPlan, str]:
    """Повертає маршрут і назву моделі, яка його склала."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError("Не задано змінну середовища GEMINI_API_KEY.")

    client = genai.Client(api_key=api_key)
    prompt = build_prompt(request, city)
    config = {
        "response_mime_type": "application/json",
        "response_json_schema": GeminiPlan.model_json_schema(),
        "temperature": 0.7,
    }

    for model in MODELS:
        for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
            try:
                response = await client.aio.models.generate_content(
                    model=model, contents=prompt, config=config)
            except errors.APIError as error:
                log.warning("Gemini %s, спроба %d: %s %s", model, attempt, error.code, error)
                if error.code in SKIP_CODES:
                    break
                if error.code in RETRY_CODES:
                    if attempt < ATTEMPTS_PER_MODEL:
                        await asyncio.sleep(1.5 * attempt)
                    continue
                if error.code in (400, 401, 403):
                    raise GeminiError("Gemini відхилив запит: перевірте ключ GEMINI_API_KEY.") from error
                raise GeminiError(f"Помилка Gemini API ({error.code}).") from error
            except Exception as error:  # мережа
                log.warning("Gemini %s, спроба %d: %s", model, attempt, error)
                continue

            try:
                return GeminiPlan.model_validate_json(response.text or ""), model
            except ValidationError:
                log.warning("Gemini %s повернув JSON не за схемою", model)
                continue

    raise GeminiError("Gemini зараз перевантажений. Спробуйте ще раз за хвилину.")
