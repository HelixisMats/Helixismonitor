FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir "paho-mqtt>=2.0.0" python-dotenv
COPY mqtt_bridge.py .
CMD ["python", "mqtt_bridge.py"]
