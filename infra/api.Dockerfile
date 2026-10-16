FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY apps/api/requirements.lock ./requirements.lock
RUN python -m pip install -r requirements.lock

COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./alembic.ini
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--loop", "app.core.event_loop:selector_loop_factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
