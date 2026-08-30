# Mô phỏng chiến lược từng mã, xem bằng Grafana

Ngày 2026-08-30. Nền: `cd29e42` + `bars_daily` vừa nạp lại (1.554 mã,
2.982.903 dòng, 2016-01-03 → 2026-08-27).

## Mục tiêu

Chọn một mã + một chiến lược + một khung thời gian trên Grafana, xem chiến lược
đó **mô phỏng ra sao trên chính mã đó**: đường vốn, các lệnh, và — bắt buộc —
**đường mua-và-giữ vẽ chồng lên**.

Grafana chỉ đọc SQL, không chạy được Python. Nên kiến trúc là:
`scripts/backtest_to_db.py` chạy mô phỏng → ghi bảng kết quả → Grafana đọc bảng.

## Giả định (nêu rõ)

1. **Đường vốn lấy từ một nguồn duy nhất.** `run_backtest` đã tính
   `equity_curve` nội bộ (`trading/backtest.py:~120`) nhưng không trả ra.
   Phơi nó ra `BacktestReport` — KHÔNG tính lại trong script. Lý do: commit
   `4ea4c8d` đã phải đi sửa đúng lỗi "một công thức tồn tại hai bản, tính trên
   hai tập bar khác nhau". Không lặp lại.
2. **Chỉ dùng chiến lược đã có trong `STRATEGIES`**: `daily_breakout`,
   `octopus_pullback`. `sma_cross` bị gỡ khỏi dict này ngày 2026-08-15 theo
   quyết định của chủ dự án — KHÔNG thêm lại.
3. **Mua-và-giữ là bắt buộc hiển thị, không phải tuỳ chọn.** `BacktestReport`
   đã có `buy_and_hold_pnl`. Bài học đã trả giá: cổ phiếu VN tăng mạnh
   2016-2026, "có lãi" chỉ đo thị trường. Panel nào khoe lãi mà không có mốc
   so sánh là panel nói dối.
4. **`filtered_bars` phải hiện ra mặt.** Số bar bị loại vì OHLC <= 0 đã được
   `run_backtest` đếm sẵn. Lọc im lặng = che giấu vấn đề dữ liệu.
5. Khung thời gian lấy từ `_TF_SPEC` sẵn có (5m…1M), không tự định nghĩa mới.

## Phạm vi phẫu thuật

ĐƯỢC sửa:
- `trading/backtest.py` — CHỈ thêm trường `equity_curve` vào `BacktestReport`
  và điền nó. Không đổi logic tính toán, không đổi chữ ký `run_backtest`.
- `trading/storage/db.py` — thêm 3 bảng + hàm ghi/đọc.
- `scripts/backtest_to_db.py` — file MỚI.
- `grafana/provisioning/dashboards/backtest.json` — file MỚI.
- `tests/test_backtest.py`, `tests/test_storage.py` — thêm test.

KHÔNG được đụng: `trading/engine/**`, `trading/broker`, `trading/risk.py`,
`trading/strategies/**`, `grafana/provisioning/dashboards/trading.json`
(dashboard đang chạy — làm file MỚI, không sửa file cũ), `docker-compose.yml`,
`config/`. Không refactor `run_backtest`. Không thêm chiến lược mới.

## Lược đồ bảng

```sql
backtest_runs(
  run_id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  symbol TEXT NOT NULL, strategy TEXT NOT NULL, timeframe TEXT NOT NULL,
  frm DATE NOT NULL, to_date DATE NOT NULL, capital DOUBLE PRECISION NOT NULL,
  realized_pnl DOUBLE PRECISION, unrealized_pnl DOUBLE PRECISION,
  buy_and_hold_pnl DOUBLE PRECISION, max_drawdown DOUBLE PRECISION,
  win_rate DOUBLE PRECISION, trades INT, filtered_bars INT
)
backtest_equity(run_id BIGINT, ts TIMESTAMPTZ, equity DOUBLE PRECISION)
backtest_fills(run_id BIGINT, ts TIMESTAMPTZ, side TEXT, qty INT,
               price DOUBLE PRECISION, fee DOUBLE PRECISION)
```

## Các bước — mỗi bước kèm cách kiểm chứng

1. `gitnexus_impact({target: "BacktestReport", direction: "upstream"})` và
   `{target: "run_backtest", direction: "upstream"}`. Báo blast radius TRƯỚC
   khi sửa. Nếu HIGH/CRITICAL thì DỪNG và báo.
   → kiểm chứng: dán kết quả impact.

2. Test TRƯỚC cho `equity_curve`: chạy `run_backtest` trên bộ bar nhỏ dựng sẵn,
   khẳng định (a) độ dài đường vốn khớp số bar sạch (không phải số bar thô),
   (b) điểm đầu bằng `capital`, (c) mỗi phần tử là `(ts, equity)` với ts lấy
   từ bar.
   → kiểm chứng: `uv run pytest tests/test_backtest.py -q` ĐỎ, dán output.

3. Thêm trường và điền. Test XANH.
   → kiểm chứng: cùng lệnh XANH, dán output. VÀ: toàn bộ suite cũ không đổi
     hành vi — `max_drawdown` của các test sẵn có phải giữ nguyên giá trị.

4. Bảng + hàm ghi/đọc trong `db.py`, có test (dùng DB test sẵn có, KHÔNG
   đụng DB thật).
   → kiểm chứng: test ĐỎ trước, XANH sau, dán cả hai.

5. `scripts/backtest_to_db.py`: CLI `--symbols A,B --strategy X --timeframe 1d
   --from ... --to ...`, ghi 1 dòng `backtest_runs` + đường vốn + lệnh cho mỗi
   mã. Chạy THẬT trên 3 mã bất kỳ có dữ liệu.
   → kiểm chứng: dán output CLI + `select symbol,trades,realized_pnl,
     buy_and_hold_pnl from backtest_runs;` cho thấy 3 dòng thật.

6. `grafana/provisioning/dashboards/backtest.json` — dashboard MỚI, biến
   `$symbol`, `$strategy`, `$timeframe` truy ra từ `backtest_runs`. Panel tối
   thiểu: (a) đường vốn chiến lược VÀ mua-và-giữ trên cùng một biểu đồ,
   (b) bảng lệnh, (c) ô số: trades / win_rate / max_drawdown / filtered_bars.
   → kiểm chứng: `docker compose restart grafana` rồi xác nhận dashboard nạp
     được và panel có dữ liệu. Dán truy vấn SQL của panel (a).

7. Không hồi quy: `uv run pytest -m "not integration" -q` (nền hiện tại **317
   passed**) + `uv run ruff check trading tests scripts`.
   → kiểm chứng: dán cả hai output.

8. `gitnexus_detect_changes()`.
   → kiểm chứng: dán kết quả, xác nhận đúng phạm vi.

## Không được làm

- KHÔNG commit, KHÔNG push — Lead audit rồi mới commit.
- KHÔNG sửa `trading.json` (dashboard đang chạy).
- KHÔNG thêm `sma_cross` vào `STRATEGIES`.
- KHÔNG chạy backfill, KHÔNG gọi API SSI, KHÔNG bật `real_trading_enabled`.
- Phát hiện ngoài phạm vi: BÁO CÁO, không tự sửa.
