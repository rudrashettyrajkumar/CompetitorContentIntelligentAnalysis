# --- frontend build stage (populated in EPIC-07) ---
FROM node:22-slim AS frontend
WORKDIR /build
# COPY frontend/ .   # enabled in EPIC-07
# RUN npm ci && npm run build

# --- python runtime ---
FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .

COPY config/ config/
COPY prompts/ prompts/
# COPY --from=frontend /build/dist frontend/dist   # enabled in EPIC-07

RUN mkdir -p data
EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
