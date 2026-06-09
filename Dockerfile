FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# shell 形式才能展开 ${PORT}；Render 注入 PORT，本地 docker run 回落 8000
CMD uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000}
