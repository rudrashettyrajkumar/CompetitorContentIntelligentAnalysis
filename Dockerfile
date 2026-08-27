# --- frontend build stage (EPIC-07) ---
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# --- python runtime ---
FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1
# Non-editable install lands under site-packages; point the code at the tree that
# actually holds config/ prompts/ frontend/ (see app/config/settings.py).
ENV APP_ROOT=/app

COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

COPY config/ config/
COPY prompts/ prompts/
COPY data/ data/
COPY docker-entrypoint.sh ./
COPY --from=frontend /build/dist frontend/dist

RUN mkdir -p data && chmod +x docker-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
# Bind $PORT when the platform injects one (Render), fall back to 8000 (Fly, compose, local).
CMD ["sh", "-c", "exec uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
