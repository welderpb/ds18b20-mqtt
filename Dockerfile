FROM python:3.14-slim

RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ds18b20_mqtt.py .

USER appuser

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "ds18b20_mqtt.py"]
