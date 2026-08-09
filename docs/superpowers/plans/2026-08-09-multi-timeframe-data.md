# VN Market History Data Implementation Plan (3 sàn, đa khung)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Đưa DB về đúng thiết kế dữ liệu đã chốt — `bars_daily` chứa ~10 năm bar
ngày cho toàn bộ mã HOSE/HNX/UPCOM; `bars` chứa bar 5m từ 01/01/2026 cho tập mã
đã lọc thanh khoản. Mọi khung khác **tính khi cần**, không lưu.

**Architecture:** Một nhánh code thuần (sửa resample) chạy độc lập, và một chuỗi
dữ liệu 4 bước nối tiếp: đo độ sâu API thật → backfill 1d toàn sàn → lọc thanh
khoản *từ chính dữ liệu 1d vừa có* → backfill 5m cho tập đã lọc. Việc lấy bộ lọc
từ dữ liệu ngày giải quyết bài toán con-gà-quả-trứng: không cần dữ liệu 5m để
biết mã nào đáng lấy 5m.

**Tech Stack:** Python 3.11+, pytest, ruff, psycopg 3, TimescaleDB, ssi-sdk.
Không thêm dependency mới.

## Thiết kế dữ liệu đã chốt (user duyệt 2026-08-09)

| Khung | Nguồn | Lưu trong DB? |
|---|---|---|
| 1d, từ 31/12/2025 trở về trước | SSI daily OHLC, **sâu tối đa API cho (~10 năm)** | **Có** — `bars_daily` |
| 1d, từ 01/01/2026 | SSI daily OHLC | **Có** — `bars_daily` |
| 5m, từ 01/01/2026 | SSI intraday OHLC | **Có** — `bars` |
| 10m, 15m, 30m, 1h, 4h | Tính từ **5m** | Không |
| 1w, 1M | Tính từ **1d** | Không |

- **KHÔNG tạo bảng `bars_1h`.** 1h suy ra hoàn toàn từ 5m; lưu riêng tạo hai
  nguồn sự thật có thể lệch nhau, tốn thêm ~1,2 triệu dòng và ~11.000 request API
  mà không thêm thông tin gì. (Quyết định của user, đã cân nhắc.)
- **Phái sinh giữ nguyên**, không đụng tới. Mã `41I1G8000` trong `bars` là dữ
  liệu phái sinh — **KHÔNG xoá** (khác với chỉ thị trong bản plan trước).
- **Streaming real-time KHÔNG đổi.** Collector vẫn chỉ stream `config.symbols`
  (VCB/HPG/TCB). Plan này chỉ nói về dữ liệu lịch sử.

## Sự thật đã đo được (đừng đo lại, đừng giả định khác)

Đo trực tiếp 2026-08-09:

- `bars`: VCB/HPG/TCB mỗi mã 276 bar 5m / 6 phiên (31/07 → 07/08). Rác spike:
  `PDB` (78), `BTCLI` (25), `BCA` (15) — và `41I1G8000` (1014, **phái sinh, giữ**).
- `bars_daily`: **1 dòng mỗi mã**, và **KHÔNG phải hypertable** (`schema.sql`
  chỉ gọi `create_hypertable` cho `bars` và `index_values`).
- `index_values`: trống — không có feed index real-time, xem
  `PLAN_INDEX_STREAMING.md`. **Không điều tra lại.**
- **Lưới bar 5m thật: 46 slot/phiên**, giống hệt nhau cả 6 ngày:
  - Sáng `09:15 → 11:25` (27 slot)
  - Chiều `13:00 → 14:25` (18 slot)
  - Rồi **nhảy thẳng tới `14:45`** (1 slot, bar ATC). Không có 14:30/14:35/14:40.
  - Không có bar trước 09:15 (đợt ATO).
- `resample_bars()` trên dữ liệu thật: 5m=276, 10m=144, 15m=96, 1h=30,
  **4h=30, 1d=30, 1w=30 — tất cả cách nhau đúng 1 giờ.** Mọi khung ≥ 60 phút đều
  sụp về bar 1 giờ, im lặng.
- Nguyên nhân: `resample.py::_bucket()` chỉ làm
  `ts.replace(minute=(ts.minute // target) * target)` — không đụng giờ/ngày.
- Bug này **hiện chưa gây hại**: `backtest.py:102` chỉ mở
  `_TF_MINUTES = {"15m": 15, "1h": 60}` và 60 tình cờ đúng; `test_resample.py`
  chỉ test 15m.

**API đã xác minh tồn tại** (không phải đoán):
- `trading/collector/backfill.py::SSIRestClient(cfg, storage)` với
  `async daily_ohlc(symbol, frm, to)`, `async intraday_ohlc(symbol, frm, to)`,
  `async close()`.
- `scripts/backfill_history.py::backfill_history(...)`.
- Liệt kê mã theo sàn: `data.market_data.get_securities_info_by_board(board)` —
  dùng trong `scripts/spike_ssi_sdk_hnx_upcom_ohlc.py:42`, trả list có `.symbol`.

## Global Constraints

- **`gitnexus_impact({target, direction: "upstream"})` trước khi sửa symbol**;
  `gitnexus_detect_changes()` sau mỗi task có sửa file. HIGH/CRITICAL → dừng, hỏi.
- **KHÔNG tự commit, KHÔNG tự push.**
- **KHÔNG chạy `ruff --fix`** ở bất kỳ đâu. Chỉ `ruff check`.
- Baseline phải giữ: `uv run pytest -m "not integration" -q` → **178 passed**.
- Postgres/NATS trong test và script: **`127.0.0.1`**, không bao giờ `localhost`
  (`localhost` → `::1` → ~130s mỗi connect trên máy này).
- Sau mỗi lần dùng Edit tool: kiểm tra `git diff --stat`, gỡ formatter churn.

---

## File Structure

| File | Trách nhiệm | Task |
|------|-------------|------|
| `trading/storage/schema.sql` | `bars_daily` → hypertable; 2 bảng mới | 1 |
| `trading/storage/db.py` | Đọc/ghi `symbol_universe`, `backfill_progress` | 1 |
| `tests/test_storage.py` | Integration test cho 2 bảng mới | 1 |
| `trading/resample.py` | Sửa `_bucket`; thêm daily/weekly/monthly | 2 |
| `tests/test_resample.py` | Test khung ≥60m, 1d, 1w, 1M, regression ≤60m | 2 |
| `trading/backtest.py` | Mở `--tf` cho đủ khung, đọc đúng bảng nguồn | 3 |
| `tests/test_backtest_cli.py` | Test danh sách khung | 3 |
| `scripts/spike_ssi_history_depth.py` | **Mới** — đo độ sâu 5m + liệt kê mã 3 sàn | 4 |
| `docs/superpowers/research/2026-08-09-ssi-history-depth.md` | **Mới** — findings | 4 |
| `scripts/backfill_universe.py` | **Mới** — backfill resumable toàn sàn | 5, 7 |
| `scripts/screen_liquidity.py` | **Mới** — lọc thanh khoản từ `bars_daily` | 6 |

---

### Task 1: Schema — hypertable cho `bars_daily` + bảng universe/checkpoint

**Files:**
- Modify: `trading/storage/schema.sql`, `trading/storage/db.py`
- Test: `tests/test_storage.py`

**Interfaces (Produces):**
- Bảng `symbol_universe(symbol PK, exchange, avg_value_20d, avg_volume_20d,
  is_active bool, updated_at)`
- Bảng `backfill_progress(symbol, timeframe, last_done_date, status, error,
  updated_at)`, PK `(symbol, timeframe)`
- `Storage.upsert_symbol_universe(rows: list[dict]) -> None`
- `Storage.read_active_universe() -> list[str]` — chỉ mã `is_active = true`
- `Storage.get_backfill_progress(symbol, timeframe) -> dict | None`
- `Storage.set_backfill_progress(symbol, timeframe, last_done_date, status, error=None) -> None`

- [ ] **Step 0: GitNexus impact**

`gitnexus_impact({target: "init_schema", direction: "upstream"})`. Dán kết quả.

- [ ] **Step 1: Viết test thất bại**

Thêm vào `tests/test_storage.py` (file integration đã có fixture `storage`;
đọc phần đầu để khớp style, nhớ dọn dữ liệu test trong fixture):

```python
def test_symbol_universe_upsert_and_read_active(storage):
    with storage.conn() as c:
        c.execute("DELETE FROM symbol_universe WHERE symbol LIKE 'ZZ%'")
    storage.upsert_symbol_universe([
        {"symbol": "ZZA", "exchange": "HOSE", "avg_value_20d": 5e9,
         "avg_volume_20d": 100000, "is_active": True},
        {"symbol": "ZZB", "exchange": "UPCOM", "avg_value_20d": 1e6,
         "avg_volume_20d": 100, "is_active": False},
    ])
    active = storage.read_active_universe()
    assert "ZZA" in active
    assert "ZZB" not in active

    # upsert lai phai GHI DE, khong tao dong trung
    storage.upsert_symbol_universe([
        {"symbol": "ZZA", "exchange": "HOSE", "avg_value_20d": 1.0,
         "avg_volume_20d": 1, "is_active": False},
    ])
    assert "ZZA" not in storage.read_active_universe()


def test_backfill_progress_roundtrip(storage):
    from datetime import date

    with storage.conn() as c:
        c.execute("DELETE FROM backfill_progress WHERE symbol = 'ZZA'")
    assert storage.get_backfill_progress("ZZA", "1d") is None

    storage.set_backfill_progress("ZZA", "1d", date(2026, 1, 31), "ok")
    got = storage.get_backfill_progress("ZZA", "1d")
    assert got["last_done_date"] == date(2026, 1, 31)
    assert got["status"] == "ok"

    storage.set_backfill_progress("ZZA", "1d", date(2026, 2, 28), "error", "boom")
    got = storage.get_backfill_progress("ZZA", "1d")
    assert got["status"] == "error" and got["error"] == "boom"


def test_bars_daily_is_hypertable(storage):
    """bars_daily se chua ~4 trieu dong (1600 ma x 10 nam); khong hypertable thi
    query theo khoang thoi gian khong duoc chunk pruning."""
    with storage.conn() as c:
        row = c.execute(
            "SELECT count(*) FROM timescaledb_information.hypertables "
            "WHERE hypertable_name = 'bars_daily'"
        ).fetchone()
    assert row[0] == 1, "bars_daily phai la hypertable"
```

- [ ] **Step 2: Chạy để xác nhận FAIL**

```bash
uv run pytest tests/test_storage.py -m integration -q -k "universe or backfill_progress or hypertable"
```
Expected: FAIL — bảng/hàm chưa tồn tại.

- [ ] **Step 3: Sửa `schema.sql`**

Thêm ngay sau khối `bars_daily` hiện có:

```sql
SELECT create_hypertable('bars_daily', 'ts', if_not_exists => TRUE, migrate_data => TRUE);

CREATE TABLE IF NOT EXISTS symbol_universe (
  symbol text PRIMARY KEY,
  exchange text NOT NULL,
  avg_value_20d double precision,
  avg_volume_20d double precision,
  is_active boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS backfill_progress (
  symbol text NOT NULL,
  timeframe text NOT NULL,
  last_done_date date,
  status text NOT NULL,
  error text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, timeframe)
);
```

`migrate_data => TRUE` an toàn ở đây vì `bars_daily` chỉ có 3 dòng. **Nếu bảng
đã lớn thì đây là thao tác nặng** — nhưng ở trạng thái hiện tại thì không.

- [ ] **Step 4: Thêm 4 method vào `trading/storage/db.py`**

Theo đúng style hiện có (`with self.conn() as c`, SQL thuần, không ORM). Đặt
cạnh các method account/derivative cho nhất quán.

```python
    def upsert_symbol_universe(self, rows: list[dict]) -> None:
        if not rows:
            return
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO symbol_universe "
                "(symbol, exchange, avg_value_20d, avg_volume_20d, is_active, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, now()) "
                "ON CONFLICT (symbol) DO UPDATE SET "
                "exchange = EXCLUDED.exchange, avg_value_20d = EXCLUDED.avg_value_20d, "
                "avg_volume_20d = EXCLUDED.avg_volume_20d, is_active = EXCLUDED.is_active, "
                "updated_at = now()",
                [
                    (
                        r["symbol"],
                        r["exchange"],
                        r.get("avg_value_20d"),
                        r.get("avg_volume_20d"),
                        r["is_active"],
                    )
                    for r in rows
                ],
            )

    def read_active_universe(self) -> list[str]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol FROM symbol_universe WHERE is_active ORDER BY symbol"
            ).fetchall()
        return [r[0] for r in rows]

    def get_backfill_progress(self, symbol: str, timeframe: str) -> dict | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT symbol, timeframe, last_done_date, status, error "
                "FROM backfill_progress WHERE symbol = %s AND timeframe = %s",
                (symbol, timeframe),
            ).fetchone()
        if row is None:
            return None
        return {
            "symbol": row[0],
            "timeframe": row[1],
            "last_done_date": row[2],
            "status": row[3],
            "error": row[4],
        }

    def set_backfill_progress(
        self,
        symbol: str,
        timeframe: str,
        last_done_date,
        status: str,
        error: str | None = None,
    ) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT INTO backfill_progress "
                "(symbol, timeframe, last_done_date, status, error, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, now()) "
                "ON CONFLICT (symbol, timeframe) DO UPDATE SET "
                "last_done_date = EXCLUDED.last_done_date, status = EXCLUDED.status, "
                "error = EXCLUDED.error, updated_at = now()",
                (symbol, timeframe, last_done_date, status, error),
            )
```

- [ ] **Step 5: Chạy test PASS + regression**

```bash
uv run pytest tests/test_storage.py -m integration -q
uv run pytest -m "not integration" -q
uv run ruff check trading tests
```
Expected: test_storage pass hết; unit vẫn 178 passed; ruff sạch.

- [ ] **Step 6: GitNexus + báo cáo (KHÔNG commit)**

---

### Task 2: Sửa `resample_bars` + thêm daily/weekly/monthly

**Files:** Modify `trading/resample.py`; Test `tests/test_resample.py`

**Interfaces (Produces):**
- `resample_bars(bars, target_minutes) -> list[Bar]` — chữ ký giữ nguyên, đúng
  cho mọi `target_minutes` kể cả > 60.
- `resample_daily(bars) -> list[Bar]` — gom theo ngày lịch VN, `ts` = 00:00 VN.
- `resample_weekly(bars) -> list[Bar]` — `ts` = 00:00 VN **thứ Hai** của tuần.
- `resample_monthly(bars) -> list[Bar]` — `ts` = 00:00 VN **ngày 1** của tháng.

**Quyết định đã chốt:** neo bucket theo **nửa đêm giờ VN**, không theo epoch UTC.
Neo UTC cho ranh giới 4h rơi vào 07:00/11:00/15:00 giờ VN — cắt đôi phiên sáng.
Neo nửa đêm VN cho 00/04/08/12/16, nên **4h = 2 bar/phiên** (08:00 ôm trọn phiên
sáng, 12:00 ôm trọn phiên chiều). VN không có DST nên `replace(hour=0)` an toàn.
Kết quả 5m/10m/15m/1h **phải không đổi** (offset VN +07:00 tròn giờ nên
phút-trong-giờ giống nhau ở UTC và VN) — có test regression khoá điều này.

- [ ] **Step 0: GitNexus impact**

`gitnexus_impact` cho `resample_bars` và `_bucket`. Dán kết quả.

- [ ] **Step 1: Viết test thất bại**

Thêm vào cuối `tests/test_resample.py`:

```python
from datetime import timedelta

from trading.calendar_vn import TZ
from trading.resample import resample_daily, resample_monthly, resample_weekly


def _session_bars(month, day, sym="VCB", price=10.0):
    """46 slot that cua 1 phien VN, khop luoi do duoc tu DB."""
    times = (
        [(9, 15 + 5 * i) for i in range(27)]  # 09:15 -> 11:25
        + [(13, 5 * i) for i in range(18)]  # 13:00 -> 14:25
        + [(14, 45)]  # bar ATC
    )
    out = []
    for h, m in times:
        ts = datetime(2026, month, day, 9, 0, tzinfo=TZ) + timedelta(
            hours=h - 9, minutes=m
        )
        out.append(Bar(sym, ts, price, price + 1, price - 1, price, 100))
    return out


def test_bucket_above_one_hour_no_longer_collapses_to_hourly():
    """4h phai ra 2 bar/phien. Bug goc: moi khung >= 60 phut deu ra bar 1 gio."""
    out = resample_bars(_session_bars(8, 3), 240)
    assert len(out) == 2, f"4h phai ra 2 bar/phien, dang ra {len(out)}"
    assert [b.ts.astimezone(TZ).strftime("%H:%M") for b in out] == ["08:00", "12:00"]


def test_resample_below_one_hour_unchanged():
    """Regression: ket qua <= 60 phut phai y het truoc khi sua.

    10m: sang 14 bucket + chieu 9 + ATC 1 = 24
    15m: sang 9 + chieu 6 + ATC 1 = 16
    1h : sang 3 (09,10,11) + chieu 2 (13,14) = 5
    """
    bars = _session_bars(8, 3)
    assert len(resample_bars(bars, 10)) == 24
    assert len(resample_bars(bars, 15)) == 16
    assert len(resample_bars(bars, 60)) == 5


def test_resample_daily_groups_by_vn_calendar_day():
    bars = _session_bars(8, 3) + _session_bars(8, 4)
    out = resample_daily(bars)
    assert len(out) == 2
    assert [b.ts.astimezone(TZ).strftime("%Y-%m-%d %H:%M") for b in out] == [
        "2026-08-03 00:00",
        "2026-08-04 00:00",
    ]
    assert out[0].open == bars[0].open
    assert out[0].close == bars[45].close
    assert out[0].volume == sum(b.volume for b in bars[:46])


def test_resample_weekly_anchors_on_monday():
    # 2026-08-03 thu Hai, 2026-08-07 thu Sau, 2026-08-10 thu Hai ke tiep
    out = resample_weekly(_session_bars(8, 3) + _session_bars(8, 7) + _session_bars(8, 10))
    assert [b.ts.astimezone(TZ).strftime("%Y-%m-%d") for b in out] == [
        "2026-08-03",
        "2026-08-10",
    ]


def test_resample_monthly_anchors_on_first_of_month():
    out = resample_monthly(_session_bars(7, 15) + _session_bars(8, 3) + _session_bars(8, 20))
    assert [b.ts.astimezone(TZ).strftime("%Y-%m-%d") for b in out] == [
        "2026-07-01",
        "2026-08-01",
    ]
```

**Các con số 24 / 16 / 5 đã tính tay từ lưới 46 slot.** Nếu chạy ra khác,
**ĐỪNG sửa số cho khớp** — tính lại từ lưới ở mục "Sự thật đã đo được", đối
chiếu. Còn lệch thì là phát hiện thật, báo cáo.

- [ ] **Step 2: Chạy để xác nhận FAIL**

```bash
uv run pytest tests/test_resample.py -v
```
Expected: `ImportError: cannot import name 'resample_daily'`.

- [ ] **Step 3: Viết lại `trading/resample.py`**

```python
from collections import defaultdict
from datetime import datetime, timedelta

from trading.calendar_vn import TZ
from trading.models import Bar


def _aggregate(symbol: str, bucket: datetime, group: list[Bar]) -> Bar:
    group = sorted(group, key=lambda b: b.ts)
    return Bar(
        symbol=symbol,
        ts=bucket,
        open=group[0].open,
        high=max(g.high for g in group),
        low=min(g.low for g in group),
        close=group[-1].close,
        volume=sum(g.volume for g in group),
        source=group[0].source,
    )


def _group_by(bars: list[Bar], key) -> list[Bar]:
    buckets: dict[tuple[str, datetime], list[Bar]] = defaultdict(list)
    for b in bars:
        buckets[(b.symbol, key(b.ts))].append(b)
    return [
        _aggregate(sym, bucket, group)
        for (sym, bucket), group in sorted(buckets.items(), key=lambda kv: kv[0])
    ]


def _vn_midnight(ts: datetime) -> datetime:
    local = ts.astimezone(TZ)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _bucket(ts: datetime, target_minutes: int) -> datetime:
    """Neo theo nua dem GIO VN, khong phai phut-trong-gio.

    Cach cu (`ts.replace(minute=...)`) khong dung toi gio/ngay nen moi khung
    >= 60 phut deu sup ve bar 1 gio ma khong bao loi. Neo nua dem VN thay vi
    epoch UTC de ranh gioi 4h roi vao 00/04/08/12/16 gio VN — bucket 08:00 om
    tron phien sang, 12:00 om tron phien chieu.
    """
    day_start = _vn_midnight(ts)
    minutes = int((ts.astimezone(TZ) - day_start).total_seconds() // 60)
    return day_start + timedelta(minutes=(minutes // target_minutes) * target_minutes)


def resample_bars(bars: list[Bar], target_minutes: int) -> list[Bar]:
    return _group_by(bars, lambda ts: _bucket(ts, target_minutes))


def resample_daily(bars: list[Bar]) -> list[Bar]:
    """Gom theo NGAY LICH gio VN.

    Khong dung resample_bars(bars, 1440): phien VN chi chiem mot phan nho cua
    ngay va bar ATC nam lech (14:45, sau khoang trong 14:30-14:40), nen gom theo
    phut se cho ranh gioi sai.
    """
    return _group_by(bars, _vn_midnight)


def resample_weekly(bars: list[Bar]) -> list[Bar]:
    """Gom theo TUAN, moc thu Hai gio VN. Dung cho bar NGAY (bars_daily)."""

    def monday(ts: datetime) -> datetime:
        d = _vn_midnight(ts)
        return d - timedelta(days=d.weekday())

    return _group_by(bars, monday)


def resample_monthly(bars: list[Bar]) -> list[Bar]:
    """Gom theo THANG, moc ngay 1 gio VN. Dung cho bar NGAY (bars_daily)."""
    return _group_by(bars, lambda ts: _vn_midnight(ts).replace(day=1))
```

- [ ] **Step 4: Test PASS**

```bash
uv run pytest tests/test_resample.py -v
```
Expected: 3 test cũ + 5 test mới đều pass.

- [ ] **Step 5: Regression + lint**

```bash
uv run pytest -m "not integration" -q
uv run ruff check trading tests
```
Expected: **183 passed** (178 + 5), ruff sạch.

- [ ] **Step 6: GitNexus + `git diff --stat` + báo cáo (KHÔNG commit)**

---

### Task 3: Mở CLI backtest cho đủ khung, đọc đúng bảng nguồn

**Files:** Modify `trading/backtest.py`; Test `tests/test_backtest_cli.py`

**Interfaces:** Consumes 4 hàm resample từ Task 2. Produces `--tf` nhận
`5m,10m,15m,30m,1h,4h,1d,1w,1M`.

**Điểm mấu chốt:** khung ≤ 4h đọc từ bảng `bars`; khung ≥ 1d đọc từ
`bars_daily`. Trước đây mọi thứ đọc từ `bars`.

- [ ] **Step 0: GitNexus impact** cho `main` trong `trading/backtest.py`.

- [ ] **Step 1: Viết test thất bại**

```python
def test_tf_registry_covers_all_timeframes_and_sources():
    from trading.backtest import _TF_SPEC

    assert set(_TF_SPEC) == {"5m", "10m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"}
    # khung noi ngay doc bang `bars`, khung tu 1d tro len doc `bars_daily`
    assert {tf for tf, (src, _) in _TF_SPEC.items() if src == "bars"} == {
        "5m", "10m", "15m", "30m", "1h", "4h"
    }
    assert {tf for tf, (src, _) in _TF_SPEC.items() if src == "bars_daily"} == {
        "1d", "1w", "1M"
    }
```

- [ ] **Step 2: Chạy để xác nhận FAIL** — `ImportError: cannot import name '_TF_SPEC'`.

- [ ] **Step 3: Sửa `trading/backtest.py`**

Đổi import (dòng ~98):
```python
from trading.resample import (
    resample_bars,
    resample_daily,
    resample_monthly,
    resample_weekly,
)
```

Thay `_TF_MINUTES` (dòng 102) bằng:
```python
# (bang_nguon, ham_resample). Khung noi ngay tinh tu bar 5m trong `bars`;
# 1d/1w/1M tinh tu `bars_daily`. Xem plan 2026-08-09-multi-timeframe-data.md.
_TF_SPEC = {
    "5m": ("bars", lambda bars: bars),
    "10m": ("bars", lambda bars: resample_bars(bars, 10)),
    "15m": ("bars", lambda bars: resample_bars(bars, 15)),
    "30m": ("bars", lambda bars: resample_bars(bars, 30)),
    "1h": ("bars", lambda bars: resample_bars(bars, 60)),
    "4h": ("bars", lambda bars: resample_bars(bars, 240)),
    "1d": ("bars_daily", lambda bars: bars),
    "1w": ("bars_daily", resample_weekly),
    "1M": ("bars_daily", resample_monthly),
}
```

Trong `main()`: đổi `choices` của `--tf` thành `list(_TF_SPEC)`; chọn bảng đọc
theo `_TF_SPEC[args.tf][0]` và áp hàm `_TF_SPEC[args.tf][1]`.

`Storage` hiện chỉ có `read_bars()` đọc bảng `bars`. Nếu cần đọc `bars_daily`,
**thêm `Storage.read_daily_bars(symbol, start, end)`** theo đúng khuôn
`read_bars` (chỉ đổi tên bảng) — đây là phần thay đổi hợp lệ của task này.
`resample_daily` không dùng ở đây vì `bars_daily` đã là bar ngày; nó dành cho
trường hợp muốn dựng 1d từ 5m, giữ trong `resample.py` cho Task khác dùng.

- [ ] **Step 4: Test PASS**

```bash
uv run pytest tests/test_backtest_cli.py -m integration -q
```
**Lưu ý:** `test_read_resample_replay_is_deterministic_from_real_db` **đang FAIL
SẴN** với `TypeError: run_backtest() missing 1 required positional argument:
'capital'` — lỗi có từ trước, **KHÔNG thuộc task này, KHÔNG sửa**; chỉ xác nhận
nó vẫn fail đúng lý do cũ.

- [ ] **Step 5: Regression + lint + báo cáo (KHÔNG commit)**

---

### Task 4: Đo độ sâu lịch sử SSI + liệt kê mã 3 sàn

**Files:** Create `scripts/spike_ssi_history_depth.py`,
`docs/superpowers/research/2026-08-09-ssi-history-depth.md`

**Đây là task đo đạc, không sửa code production.** Kết quả quyết định tham số
của Task 5 và 7.

- [ ] **Step 1: Viết spike**

Đọc `scripts/backfill_history.py`, `trading/collector/backfill.py` và
`scripts/spike_ssi_sdk_hnx_upcom_ohlc.py` TRƯỚC. **Dùng lại `SSIRestClient` và
`get_securities_info_by_board` đã có — không tự viết HTTP call mới.**

Spike phải trả lời đúng 3 câu:

1. **Mỗi sàn có bao nhiêu mã?** Gọi `get_securities_info_by_board` cho HOSE,
   HNX, UPCOM. In số lượng + 5 mã đầu mỗi sàn. Lưu danh sách đầy đủ ra
   `scripts/.spike_all_symbols.json` (gitignored — thêm dòng vào `.gitignore`).
2. **Daily lùi được bao xa?** Với VCB (HOSE), gọi `daily_ohlc` cho cửa sổ 1 tháng
   tại các mốc lùi dần: 1, 2, 3, 5, 7, 10 năm. Ghi số bar mỗi mốc.
3. **5m lùi được bao xa?** Với VCB, gọi `intraday_ohlc` cho cửa sổ **1 phiên**
   tại các mốc lùi: 7, 30, 60, 90, 180, 365 ngày. Ghi số bar mỗi mốc.
   **Đây là câu quan trọng nhất** — nếu SSI không trả 5m về tới 01/01/2026 thì
   yêu cầu của user không thực hiện được và phải báo ngay.

In bảng dạng:
```
[san] HOSE: 412 ma | HNX: 328 ma | UPCOM: 876 ma
[daily] lui  1 nam (2025-08): 21 bar
[daily] lui 10 nam (2016-08): 0 bar   <-- het du lieu
[5m]    lui 30 ngay (2026-07-10): 46 bar
[5m]    lui 365 ngay (2025-08-09): 0 bar  <-- het du lieu
```

- [ ] **Step 2: Chạy thật**

```bash
uv run python -m scripts.spike_ssi_history_depth
```
Thiếu credential SSI hoặc auth hỏng → **DỪNG, báo cáo, KHÔNG đoán số**.

- [ ] **Step 3: Ghi findings**

`docs/superpowers/research/2026-08-09-ssi-history-depth.md`: output dán nguyên
văn, kết luận rõ **ngày sớm nhất có bar 5m** và **ngày sớm nhất có bar 1d**, số
mã mỗi sàn, ngày chạy. Không dùng từ "khoảng"/"có lẽ".

**Nếu 5m không lùi được tới 01/01/2026:** ghi rõ mốc sớm nhất thật sự, và nêu
rằng Task 7 chỉ backfill được từ mốc đó. Đây là kết quả hợp lệ, không phải thất bại.

- [ ] **Step 4: Báo cáo (KHÔNG commit)**

---

### Task 5: Backfill 1d toàn bộ 3 sàn (resumable)

**Files:** Create `scripts/backfill_universe.py`

**Interfaces (Produces):** CLI
`python -m scripts.backfill_universe --timeframe 1d --from YYYY-MM-DD --to YYYY-MM-DD [--exchanges HOSE,HNX,UPCOM] [--symbols A,B] [--limit N]`

**Yêu cầu thiết kế (không thương lượng):**
- **Resumable.** Trước mỗi mã, đọc `get_backfill_progress(symbol, timeframe)`;
  nếu `status == "ok"` và `last_done_date >= to` thì **bỏ qua**. Sau mỗi mã
  thành công, ghi `set_backfill_progress(..., "ok")`. Job này chạy hàng giờ —
  lỗi giữa chừng không được bắt chạy lại từ đầu.
- **Lỗi 1 mã không được giết cả job.** Bọc try/except **quanh từng mã**, ghi
  `status="error"` + thông điệp, rồi đi tiếp. (Đúng bài học commit `ed017c9`:
  trước đây một mã lỗi làm hỏng cả vòng lặp.)
- **In tiến độ định kỳ**: cứ 25 mã in `[i/N] symbol ... n bar` + số lỗi tích luỹ.
- **Tôn trọng rate limit**: `--sleep-ms` mặc định 200ms giữa các lời gọi. Nếu
  gặp lỗi rate-limit từ SSI, chờ luỹ tiến (1s, 2s, 4s… tối đa 60s) rồi thử lại
  tối đa 3 lần cho **cùng một** mã trước khi đánh `error`.
- Ghi bar qua `storage.write_daily()` (1d) / `storage.write_bars()` (5m) — cả
  hai đã UPSERT theo `(symbol, ts)` nên chạy lại an toàn, không nhân bản dữ liệu.
- Danh sách mã: đọc từ `scripts/.spike_all_symbols.json` (Task 4) nếu có, nếu
  không thì gọi `get_securities_info_by_board` trực tiếp.

- [ ] **Step 1: Chạy thử trên tập nhỏ trước khi chạy toàn sàn**

```bash
uv run python -m scripts.backfill_universe --timeframe 1d \
    --from 2016-01-01 --to 2025-12-31 --symbols VCB,HPG,TCB
```
Kiểm chứng: `bars_daily` có dữ liệu 3 mã, `backfill_progress` có 3 dòng
`status='ok'`. **Chạy lại đúng lệnh đó lần 2** → phải bỏ qua cả 3 mã (in "skip"),
không gọi API lần nữa. Đây là bằng chứng resumable hoạt động.

- [ ] **Step 2: Chạy toàn bộ 3 sàn**

Dùng ngày sớm nhất đo được ở Task 4 (không đoán):
```bash
uv run python -m scripts.backfill_universe --timeframe 1d \
    --from <NGAY_SOM_NHAT_DO_DUOC> --to 2025-12-31 \
    --exchanges HOSE,HNX,UPCOM
```
Rồi phần từ 01/01/2026 tới hôm nay:
```bash
uv run python -m scripts.backfill_universe --timeframe 1d \
    --from 2026-01-01 --to <HOM_NAY> --exchanges HOSE,HNX,UPCOM
```

Job này **chạy nhiều giờ**. Chạy nền, đừng ngồi chờ đồng bộ. Nếu bị ngắt, chạy
lại đúng lệnh — checkpoint lo phần còn lại.

- [ ] **Step 3: Kiểm chứng**

```bash
uv run python -c "
import psycopg
with psycopg.connect('postgresql://trading:trading@127.0.0.1:5432/trading') as c:
    print('so ma:', c.execute('SELECT count(DISTINCT symbol) FROM bars_daily').fetchone()[0])
    print('so dong:', c.execute('SELECT count(*) FROM bars_daily').fetchone()[0])
    print('khoang:', c.execute('SELECT min(ts)::date, max(ts)::date FROM bars_daily').fetchone())
    print('loi:', c.execute(\"SELECT count(*) FROM backfill_progress WHERE timeframe='1d' AND status='error'\").fetchone()[0])
    print('vd 5 loi dau:', c.execute(\"SELECT symbol, error FROM backfill_progress WHERE timeframe='1d' AND status='error' LIMIT 5\").fetchall())
"
```
Báo cáo đủ 5 con số. Có mã lỗi là bình thường (mã huỷ niêm yết, mã mới) —
**liệt kê ra, đừng giấu**.

- [ ] **Step 4: Báo cáo (KHÔNG commit)**

---

### Task 6: Lọc thanh khoản → điền `symbol_universe`

**Files:** Create `scripts/screen_liquidity.py`

**Interfaces:** CLI
`python -m scripts.screen_liquidity [--window-days 20] [--min-value 1e9] [--dry-run]`

Tính từ **`bars_daily`** (đã có sau Task 5), không gọi API:
`avg_value_20d = avg(close * volume)` trên N phiên gần nhất mỗi mã;
`avg_volume_20d = avg(volume)`.

- [ ] **Step 1: In phân bố ở nhiều ngưỡng TRƯỚC khi ghi**

Chạy `--dry-run` in bảng:
```
nguong >= 0.5 ty VND/phien:  812 ma
nguong >= 1   ty VND/phien:  634 ma
nguong >= 5   ty VND/phien:  312 ma
nguong >= 10  ty VND/phien:  198 ma
nguong >= 20  ty VND/phien:  121 ma
```
Kèm phân bố theo sàn. **Dán bảng này vào báo cáo và DỪNG LẠI hỏi user chọn
ngưỡng** trước khi ghi `is_active`. Ngưỡng quyết định khối lượng của Task 7
(mỗi mã ≈ 7 request API), nên đây là quyết định của user, không phải của agent.

Mặc định đề xuất nếu user không chọn: **1 tỷ VND/phiên** — đủ loại mã UPCOM gần
như không giao dịch, vẫn giữ phần lớn mã có thể vào lệnh thật.

- [ ] **Step 2: Ghi universe với ngưỡng đã chốt**

```bash
uv run python -m scripts.screen_liquidity --min-value <NGUONG_USER_CHON>
```
Kiểm chứng: `storage.read_active_universe()` trả đúng số mã khớp bảng ở Step 1.

- [ ] **Step 3: Báo cáo (KHÔNG commit)**

---

### Task 7: Backfill 5m từ 01/01/2026 cho universe đã lọc

**Files:** Không tạo file mới — dùng lại `scripts/backfill_universe.py` (Task 5).

- [ ] **Step 1: Chạy thử 3 mã**

```bash
uv run python -m scripts.backfill_universe --timeframe 5m \
    --from 2026-01-01 --to <HOM_NAY> --symbols VCB,HPG,TCB
```
Kiểm chứng: VCB có ≫ 276 bar (trước đây chỉ 6 phiên), và lưới slot vẫn đúng
(09:15 → 14:45, 46 slot/phiên).

- [ ] **Step 2: Chạy toàn bộ universe**

```bash
uv run python -m scripts.backfill_universe --timeframe 5m \
    --from <NGAY_SOM_NHAT_5M_DO_DUOC> --to <HOM_NAY> --use-universe
```
`--use-universe` đọc `storage.read_active_universe()`. **Dùng ngày sớm nhất đo
được ở Task 4** — nếu SSI không có 5m từ 01/01/2026 thì lấy từ mốc thật sự có.

Job dài nhất trong plan. Chạy nền, có checkpoint.

- [ ] **Step 3: Kiểm chứng cuối — bảng số bar theo từng khung**

```bash
uv run python -c "
import psycopg
from trading.models import Bar
from trading.resample import resample_bars, resample_weekly, resample_monthly
dsn='postgresql://trading:trading@127.0.0.1:5432/trading'
with psycopg.connect(dsn) as c:
    b=[Bar(*r) for r in c.execute(\"SELECT symbol,ts,open,high,low,close,volume,source FROM bars WHERE symbol='VCB' ORDER BY ts\").fetchall()]
    d=[Bar(*r) for r in c.execute(\"SELECT symbol,ts,open,high,low,close,volume,source FROM bars_daily WHERE symbol='VCB' ORDER BY ts\").fetchall()]
print('5m ',len(b)); print('10m',len(resample_bars(b,10))); print('15m',len(resample_bars(b,15)))
print('30m',len(resample_bars(b,30))); print('1h ',len(resample_bars(b,60))); print('4h ',len(resample_bars(b,240)))
print('1d ',len(d)); print('1w ',len(resample_weekly(d))); print('1M ',len(resample_monthly(d)))
"
```

**Tiêu chí đạt: mọi khung ≥ 100 bar** (warm-up chiến lược cần ~20: SMA slow=20,
volume_period=20, RSI/ATR=14; 100 mới đủ để phân tích chứ không chỉ khởi động).
Khung nào không đạt: ghi số thật + lý do, **đừng che**.

- [ ] **Step 4: Đo dung lượng đĩa**

```bash
uv run python -c "
import psycopg
with psycopg.connect('postgresql://trading:trading@127.0.0.1:5432/trading') as c:
    for t in ('bars','bars_daily'):
        print(t, c.execute(f\"SELECT pg_size_pretty(hypertable_size('{t}'))\").fetchone()[0])
"
```
Báo cáo con số. Nếu vượt vài GB, nêu ra để user quyết có bật TimescaleDB
compression hay không — **không tự bật**, đó là quyết định riêng.

- [ ] **Step 5: Báo cáo (KHÔNG commit)**

---

## Tiêu chí nghiệm thu toàn plan

1. `uv run pytest -m "not integration" -q` → **183 passed**.
2. `uv run pytest -m integration -q` → không phát sinh lỗi mới ngoài 3 lỗi đã
   biết (2 ở `test_engine_main.py`, 1 ở `test_backtest_cli.py`).
3. `uv run ruff check trading tests` → `All checks passed!`
4. `bars_daily` là hypertable, có dữ liệu ≥ 1.000 mã, khoảng thời gian phủ tới
   31/12/2025 trở về trước theo độ sâu đo được.
5. `symbol_universe` có `is_active` đúng theo ngưỡng user chốt.
6. `bars` có dữ liệu 5m từ mốc sớm nhất đo được cho toàn bộ universe.
7. Chạy lại `backfill_universe` lần 2 → bỏ qua các mã đã `ok` (chứng minh
   checkpoint hoạt động).
8. Bảng số bar theo 9 khung ở Task 7 Step 3.
9. Không có commit/push nào do agent tạo ra.

## Ngoài phạm vi (cố ý không làm)

- **Không đụng dữ liệu phái sinh.** Mã `41I1G8000` trong `bars` giữ nguyên.
- **Không đổi streaming real-time.** Collector vẫn chỉ stream `config.symbols`.
- Không tạo bảng `bars_1h` (1h tính từ 5m).
- Không bật TimescaleDB compression (báo cáo dung lượng, để user quyết).
- `run_backtest()` thiếu tham số `capital` ở `tests/test_backtest_cli.py` — lỗi
  có sẵn. **Báo cáo, không sửa.**
- 2 test fail sẵn ở `tests/test_engine_main.py` (ATR sizing vs fixture cũ).
- Index streaming (VNINDEX/VN30) — đã kết luận không có nguồn real-time, xem
  `PLAN_INDEX_STREAMING.md`. **Không điều tra lại.**
- Mã spike `PDB`/`BTCLI`/`BCA` trong `bars`: để yên. `BTCLI` là dữ liệu test tự
  sinh; hai mã kia vô hại và sẽ bị lu mờ sau backfill.
