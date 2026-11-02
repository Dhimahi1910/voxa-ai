FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY alembic.ini pytest.ini ./
COPY alembic ./alembic
COPY app ./app
COPY config ./config
COPY tests ./tests

RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
EXPOSE 8000

# Migrations are idempotent, so applying them on every start is safe. One worker: the scheduler runs in-process.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
