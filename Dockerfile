FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 APP_ENV=production
WORKDIR /app
COPY backend/requirements-mini.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/next_api.py ./next_api.py
COPY backend/mini ./mini
EXPOSE 8000
CMD ["sh", "-c", "uvicorn next_api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --limit-concurrency 32 --timeout-keep-alive 5"]
