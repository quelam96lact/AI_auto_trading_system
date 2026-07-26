# Prompt thực thi: Fix #1 — persist `real_risk.halted_date` (mất cơ chế ngắt lỗ khi engine restart)

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PLAN_REAL_ORDER_PLACEMENT.md` — đây là fix rủi ro **cao nhất** đã audit trong toàn bộ tính năng lệnh thật.

---

## ⚠️ Bối cảnh — vì sao đây là fix ưu tiên cao nhất

`RiskManager.halted_date` (cờ ngắt giao dịch khi lỗ vượt ngưỡng ngày, `max_daily_loss_pct`) chỉ tồn tại **trong bộ nhớ tiến trình** — `field(default=None, init=False)` trong `trading/risk.py`, chưa từng được lưu DB. Trong `trading/engine/main.py::run()`:
```python
real_risk = RiskManager(capital=cfg.real_order_capital)
```
được tạo **mới hoàn toàn** mỗi lần engine khởi động. Kịch bản thật: lỗ vượt ngưỡng ngày → `real_risk.halted_date` được set → engine crash/restart (docker restart, deploy, hết RAM...) → tiến trình mới tạo `real_risk` sạch, `halted_date=None` → **hệ thống lại cho phép đặt lệnh thật trong cùng ngày đã lỗ vượt ngưỡng**, đúng lúc cơ chế bảo vệ quan trọng nhất lẽ ra phải giữ.

**Chỉ fix cho `real_risk` (lệnh thật), KHÔNG fix cho `risk` (paper)** — paper trading không liên quan tiền thật, không cần tăng phạm vi ảnh hưởng không cần thiết.

**Lưu ý quan trọng:** `RiskManager.approve()` đã tự "hết hạn" halt đúng ngày mới (`if self.halted_date == today: return False` — sang ngày khác, `today` đổi, check tự false) — nghĩa là fix này CHỈ cần khôi phục đúng giá trị `halted_date` đã lưu khi khởi động, KHÔNG cần thêm logic "clear" thủ công nào khác.

---

## ⚠️ Giới hạn phạm vi

**Chỉ sửa 3 file:** `trading/storage/schema.sql` (bảng mới), `trading/storage/db.py` (2 method mới), `trading/engine/main.py` (khôi phục lúc start + lưu khi chuyển trạng thái).

**KHÔNG sửa:** `trading/risk.py` (không đổi `RiskManager` class — việc lưu/khôi phục nằm ở tầng engine, không phải risk logic), `trading/real_orders.py`, `scripts/confirm_real_order.py`.

**Trước khi sửa `trading/engine/main.py::run()`:** chạy `gitnexus_impact({target: "run", direction: "upstream"})`, báo cáo blast radius trước khi sửa.

**KHÔNG tự commit, không tự push.**

---

## Task A — Bảng mới `trading/storage/schema.sql`

```sql
CREATE TABLE IF NOT EXISTS real_risk_state (
  id integer PRIMARY KEY DEFAULT 1,
  halted_date date,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (id = 1)
);
```
(Single-row upsert table, cùng style với `engine_state`/`ssi_auth_state` đã có.)

## Task B — `trading/storage/db.py`

Thêm 2 method:
```python
def save_real_risk_halt(self, halted_date: date) -> None:
    with self.conn() as c:
        c.execute(
            "INSERT INTO real_risk_state (id, halted_date, updated_at) VALUES (1, %s, now()) "
            "ON CONFLICT (id) DO UPDATE SET halted_date = EXCLUDED.halted_date, updated_at = now()",
            (halted_date,),
        )

def read_real_risk_halt(self) -> date | None:
    with self.conn() as c:
        row = c.execute("SELECT halted_date FROM real_risk_state WHERE id = 1").fetchone()
    return row[0] if row else None
```

**Kiểm chứng:** Thêm test vào `tests/test_storage.py` (integration, cần Postgres thật):
- `test_save_and_read_real_risk_halt` — save 1 ngày cụ thể, đọc lại khớp.
- `test_read_real_risk_halt_returns_none_when_never_set` — chưa từng gọi `save_real_risk_halt` → trả về `None`.
- `test_save_real_risk_halt_upsert` — gọi save 2 lần với 2 ngày khác nhau → đọc lại khớp lần gọi sau cùng (upsert, không phải insert lỗi trùng khoá).

## Task C — `trading/engine/main.py`

1. Sau dòng `real_risk = RiskManager(capital=cfg.real_order_capital)`, thêm khôi phục:
   ```python
   real_risk.halted_date = storage.read_real_risk_halt()
   ```

2. Trong vòng lặp chính, theo đúng pattern đã có cho `risk` (paper) — hiện tại:
   ```python
   was_halted = risk.halted_date
   fills = process_bar(bar, broker, strategy, risk, marks, on_signal=on_real_signal)
   persist_fills(fills)
   if risk.halted_date is not None and risk.halted_date != was_halted:
       alert("CRITICAL", "risk halt: max daily loss reached", date=str(risk.halted_date))
   ```
   Thêm tương tự cho `real_risk` (lưu ý: `on_real_signal` gọi `real_orders.handle_signal()` bên trong `process_bar()`, có thể làm `real_risk.halted_date` thay đổi ngay trong lệnh gọi `process_bar()` đó — nên bắt `was_real_halted` TRƯỚC lệnh gọi `process_bar()`, kiểm tra và lưu NGAY SAU):
   ```python
   was_halted = risk.halted_date
   was_real_halted = real_risk.halted_date
   fills = process_bar(bar, broker, strategy, risk, marks, on_signal=on_real_signal)
   persist_fills(fills)
   if risk.halted_date is not None and risk.halted_date != was_halted:
       alert("CRITICAL", "risk halt: max daily loss reached", date=str(risk.halted_date))
   if real_risk.halted_date is not None and real_risk.halted_date != was_real_halted:
       storage.save_real_risk_halt(real_risk.halted_date)
       alert("CRITICAL", "REAL risk halt: max daily loss reached", date=str(real_risk.halted_date))
   ```

**Kiểm chứng:** Đọc `tests/test_engine_main.py` trước để khớp style (đặc biệt cách test hiện có `test_engine_alerts_critical_on_risk_halt` cho paper risk — viết test tương tự cho real). Thêm:
- `test_engine_run_persists_real_risk_halt_on_transition` — dựng kịch bản khiến `real_risk` bị halt (dùng `monkeypatch` set `cfg.real_order_capital` rất nhỏ + tạo daily_pnl âm lớn qua fake `real_orders.handle_signal`, HOẶC đơn giản hơn: `monkeypatch.setattr` thẳng vào `real_risk.approve` để giả lập set `halted_date` — chọn cách nào đơn giản nhất để test, miễn xác nhận đúng `storage.save_real_risk_halt` được gọi đúng ngày khi `real_risk.halted_date` chuyển từ `None` sang có giá trị).
- `test_engine_run_restores_real_risk_halt_on_startup` — seed `storage.save_real_risk_halt(some_date)` trước khi gọi `run()`, xác nhận `real_risk.halted_date` (truy cập qua closure/biến cục bộ nếu cần refactor nhỏ để test được, hoặc xác nhận gián tiếp qua hành vi — ví dụ real_orders.handle_signal không được gọi/không tạo pending order nếu ngày đó đang bị halt) đã được khôi phục đúng.

Chạy toàn bộ suite: `docker compose up -d postgres nats && uv run pytest -v` — pass hết.

---

## Báo cáo lại

1. Diff đầy đủ 3 file + test.
2. Output đầy đủ `uv run pytest -v`.
3. Kết quả `gitnexus_impact`/`gitnexus_detect_changes`.

Không tự commit — chờ Claude audit.
