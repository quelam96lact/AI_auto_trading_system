FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY trading ./trading
COPY config ./config
RUN pip install --no-cache-dir .
CMD ["python", "-m", "trading.collector.main", "--config", "config/config.yaml"]