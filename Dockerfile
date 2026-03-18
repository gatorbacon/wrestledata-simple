FROM python:3.11-slim

WORKDIR /app

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["python", "api/server.py"]
