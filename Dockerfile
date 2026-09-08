# ---- Stage build: co uv, co toolchain. Moi thu o day BI VUT DI. ----
FROM python:3.12-slim AS builder
WORKDIR /app

# uv + uv.lock thay cho `pip install .`: build phai TAI LAP DUOC. `pip install .`
# bo qua uv.lock, nen moi lan build lai co the keo ve phien ban ssi-sdk /
# ssi-fc-data khac voi phien ban da duoc kiem chung — hanh vi parser/stream doi
# ma khong ai biet. Repo nay co han lich su dieu tra hanh vi THAT cua SDK
# (xem PLAN_INDEX_STREAMING.md), khong duoc de dependency troi noi.
RUN pip install --no-cache-dir uv==0.12.1

# THU TU LAYER CO CHU DICH: cai dependency TRUOC khi copy code. Dependency chi
# doi khi pyproject/uv.lock doi (hiem); code doi moi ngay. Neu copy code truoc
# thi moi lan sua 1 dong Python la layer dependency 35.6MB bi dung lai tu dau.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Gio moi den code. Layer tren van hit cache khi chi co code doi.
COPY trading ./trading
COPY config ./config
RUN uv sync --frozen --no-dev

# ---- Stage runtime: khong co uv, khong co pip metadata cua uv. ----
FROM python:3.12-slim
WORKDIR /app

# Khong chay production bang root. Tao user TRUOC khi copy de dung --chown:
# `RUN chown -R` sau khi copy se ghi lai toan bo file da doi chu thanh mot
# layer nhan ban (31.3MB o ban cu).
RUN useradd --create-home --uid 10001 appuser

# WORKDIR PHAI la /app: `trading` duoc cai EDITABLE, file
# __editable__.trading-0.1.0.pth trong .venv tro cung vao /app/trading.
# Doi WORKDIR o stage nay se lam `import trading` gay.
COPY --from=builder --chown=appuser:appuser /app/.venv ./.venv
COPY --from=builder --chown=appuser:appuser /app/trading ./trading
COPY --from=builder --chown=appuser:appuser /app/config ./config

ENV PATH="/app/.venv/bin:$PATH"
USER appuser

CMD ["python", "-m", "trading.collector.main", "--config", "config/config.yaml"]
