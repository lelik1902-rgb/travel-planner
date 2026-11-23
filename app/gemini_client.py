"""Генерація маршруту через Google Gemini API зі structured output (JSON-схема)."""

import os

from google import genai
from pydantic import ValidationError

from .models import City, GeminiPlan, PlanRequest

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

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


async def generate_plan(request: PlanRequest, city: City) -> GeminiPlan:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiError("Не задано змінну середовища GEMINI_API_KEY.")

    client = genai.Client(api_key=api_key)
    try:
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=build_prompt(request, city),
            config={
                "response_mime_type": "application/json",
                "response_json_schema": GeminiPlan.model_json_schema(),
                "temperature": 0.7,
            },
        )
    except Exception as error:  # мережа, квота, неправильний ключ
        raise GeminiError(f"Помилка Gemini API: {error}") from error

    try:
        return GeminiPlan.model_validate_json(response.text or "")
    except ValidationError as error:
        raise GeminiError("Gemini повернув відповідь у неочікуваному форматі.") from error
