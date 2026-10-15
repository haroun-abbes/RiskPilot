FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 RISKPILOT_DATA_DIR=/data
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m riskpilot && mkdir -p /data && chown riskpilot /data
USER riskpilot
EXPOSE 8000
CMD ["uvicorn", "riskpilot.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "75"]
