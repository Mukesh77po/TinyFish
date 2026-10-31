# TenderHawk API (FastAPI + agents + delivery). Built by `docker compose --profile app up`.
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY alembic.ini .
COPY agents agents
COPY api api
COPY delivery delivery
EXPOSE 8000
# Migrate, make sure the demo profile exists, then serve.
CMD ["sh", "-c", "alembic upgrade head && python -m delivery.seed && uvicorn api.main:app --host 0.0.0.0 --port 8000"]
