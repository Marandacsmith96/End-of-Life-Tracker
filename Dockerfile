# Hosted copy of the Quality-of-Life Tracker.
# Set PET_QOL_PASSCODE, and mount a persistent disk at /data.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-deploy.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-deploy.txt
COPY . .
ENV PET_QOL_DATA_DIR=/data PORT=8000
EXPOSE 8000
CMD gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120 "app:create_app()"
