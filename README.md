# Планувальник подорожей (Gemini API + OpenStreetMap)

Лабораторна робота 2 з дисципліни «Хмарні обчислення», група ТК-42.

Вебсервіс складає маршрут подорожі по днях. Користувач вказує місто, кількість днів, темп, бюджет та інтереси й отримує маршрут на мапі.

## Як це працює

```
Браузер ──POST /api/plan──► FastAPI (Render)
                              │ 1. Nominatim (OpenStreetMap): чи існує місто, його центр і межі
                              │ 2. Gemini API: маршрут у форматі JSON за Pydantic-схемою
                              │ 3. Перевірка: чи лежать точки від Gemini в межах міста
Браузер ◄────── JSON ─────────┘ → список місць по днях + мапа Leaflet
```

| Компонент | Призначення |
|---|---|
| `app/main.py` | FastAPI: сторінка `/`, `GET /api/health`, `POST /api/plan` |
| `app/gemini_client.py` | Промпт і виклик Gemini (`google-genai`, structured output) |
| `app/geocoding.py` | Пошук міста через Nominatim, перевірка координат |
| `app/models.py` | Pydantic-моделі запиту, схеми Gemini та відповіді |
| `app/static/` | Сторінка з формою та мапою (Leaflet + тайли OpenStreetMap) |
| `tests/` | pytest із підставними відповідями Gemini та OSM |

Основна модель: `gemini-3.5-flash-lite`, запасні: `gemini-3.5-flash` і `gemini-2.5-flash`. Якщо модель перевантажена (503) або тимчасово недоступна, сервіс повторює запит і переходить до наступної моделі. Список задається змінною `GEMINI_MODELS` через кому.

## Локальний запуск

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY="ваш_ключ"      # https://aistudio.google.com/apikey
uvicorn app.main:app --reload
```
Сторінка відкривається за адресою http://127.0.0.1:8000, документація API — за адресою http://127.0.0.1:8000/docs.

## Тести

```bash
pytest -q
```
Тести не звертаються до мережі. Gemini та Nominatim у них замінено підставними відповідями.

## Розгортання на Render

1. New → **Blueprint** (або Web Service) → підключити цей репозиторій. Налаштування беруться з `render.yaml`.
2. У змінних середовища задати `GEMINI_API_KEY`.
3. Після збірки сервіс доступний за адресою `https://<назва>.onrender.com`.

На безкоштовному тарифі сервіс «засинає» після 15 хв простою, тому перший запит після паузи триває ~30–60 с.
