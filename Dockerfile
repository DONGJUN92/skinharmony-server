# PlayMCP in KC 배포용 — 반드시 linux/amd64로 빌드
# docker build --platform linux/amd64 -t skinharmony:latest .
FROM --platform=linux/amd64 python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY core/ core/
COPY data/ data/

ENV PORT=8000
EXPOSE 8000

CMD ["python", "server.py"]
