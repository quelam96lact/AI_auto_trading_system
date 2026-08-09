FROM python:3.12-slim
WORKDIR /app

# uv + uv.lock thay cho `pip install .`: build phai TAI LAP DUOC. `pip install .`
# bo qua uv.lock, nen moi lan build lai co the keo ve phien ban ssi-sdk /
# ssi-fc-data khac voi phien ban da duoc kiem chung — hanh vi parser/stream doi
# ma khong ai biet. Repo nay co han lich su dieu tra hanh vi THAT cua SDK
# (xem PLAN_INDEX_STREAMING.md), khong duoc de dependency troi noi.
RUN pip install --no-cache-dir uv==0.12.1

COPY pyproject.toml uv.lock ./
COPY trading ./trading
COPY config ./config
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

# Khong chay production bang root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-m", "trading.collector.main", "--config", "config/config.yaml"]
