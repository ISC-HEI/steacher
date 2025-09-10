# Stage 1: Frontend Build
FROM node:20 AS builder

WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json ./
RUN npm install

# Copy frontend source and build
COPY frontend/ ./frontend/
COPY tsconfig.json .
COPY rollup.codemirror.config.mjs .
RUN npm run build:codemirror && npx tsc


# Stage 2: Python Application
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update \
  && apt-get install -y build-essential libpq-dev \
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Copy built frontend assets from the builder stage
COPY --from=builder /app/static/js/dist/ /app/static/js/dist/
COPY --from=builder /app/node_modules/ /app/node_modules/


# Entrypoint (New Relic + Gunicorn gthread)
ENTRYPOINT ["sh","-c","NEW_RELIC_CONFIG_FILE=${NEW_RELIC_CONFIG_FILE:-/app/steacher_app/newrelic.ini} newrelic-admin run-program gunicorn exam_project.wsgi:application --worker-class gthread --workers ${WEB_CONCURRENCY:-5} --threads ${WEB_THREADS:-20} --timeout ${WEB_TIMEOUT:-180} --keep-alive 5 --graceful-timeout 30 --max-requests 1000 --max-requests-jitter 100 --bind 0.0.0.0:8000 --log-level info"]
