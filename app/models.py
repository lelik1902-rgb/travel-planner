"""Pydantic-моделі: запит користувача, схема відповіді Gemini та відповідь API."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PlanRequest(BaseModel):
    """Що вводить користувач у формі."""

    city: str = Field(min_length=2, max_length=80)
    days: int = Field(ge=1, le=5)
    interests: list[str] = Field(default_factory=list, max_length=6)
    pace: Literal["relaxed", "normal", "intense"] = "normal"
    budget: Literal["low", "medium", "high"] = "medium"

    @field_validator("city")
    @classmethod
    def strip_city(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Вкажіть назву міста.")
        return value

    @field_validator("interests")
    @classmethod
    def clean_interests(cls, value: list[str]) -> list[str]:
        return [item.strip()[:40] for item in value if item.strip()]


# --- Схема, яку ми вимагаємо від Gemini (structured output) ---

class Stop(BaseModel):
    time: str = Field(description="Час початку у форматі HH:MM")
    name: str = Field(description="Офіційна назва місця")
    description: str = Field(description="1-2 речення: що робити й чому варто відвідати")
    duration_min: int = Field(description="Орієнтовна тривалість у хвилинах")
    lat: float = Field(description="Широта місця")
    lon: float = Field(description="Довгота місця")


class DayPlan(BaseModel):
    day: int
    title: str = Field(description="Коротка тема дня")
    stops: list[Stop]


class GeminiPlan(BaseModel):
    summary: str = Field(description="2-3 речення про маршрут загалом")
    days: list[DayPlan]
    tips: list[str] = Field(description="3-5 практичних порад для мандрівника")


# --- Відповідь нашого API ---

class City(BaseModel):
    name: str
    display_name: str
    lat: float
    lon: float
    bbox: tuple[float, float, float, float]  # south, north, west, east


class CheckedStop(Stop):
    verified: bool = Field(description="Чи лежить точка в межах міста за даними OpenStreetMap")


class CheckedDay(BaseModel):
    day: int
    title: str
    stops: list[CheckedStop]


class PlanResponse(BaseModel):
    city: City
    summary: str
    days: list[CheckedDay]
    tips: list[str]
    model: str
