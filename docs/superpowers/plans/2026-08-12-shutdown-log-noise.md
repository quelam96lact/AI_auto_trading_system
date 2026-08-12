# Kế hoạch: dọn traceback giả ở log shutdown của engine

Ngày giao: 2026-08-12. Nhánh: `feature/data-layer`. Base: `f37faf9`.

## Vấn đề

Mỗi lần `docker compose stop engine` (thoát sạch, exit 0, ~0.5s), log vẫn in:

```
Task exception was never retrieved
future: <Task finished ... next_msg() ... exception=ConnectionClosedError()>
```

**Hành vi đã đúng, không có bug chức năng.** Đây thuần tuý là log bẩn.

## Nguyên nhân (đã truy, không phải suy đoán)

- `trading/engine/main.py:144` — `next_task.cancel()` rồi `break` ngay ở dòng
  145. Task bị yêu cầu huỷ nhưng **không bao giờ được `await`**.
- `trading/engine/main.py:199` — `finally: await nc.close()` đóng connection
  trong lúc task đó vẫn đang chờ.
- Task kết thúc với `ConnectionClosedError`, không ai lấy kết quả → asyncio in
  traceback lúc thu gom rác.

## Vì sao đáng sửa dù chỉ là log

Hệ thống cảnh báo của dự án dựa trên log (`trading/alerts.py`). Một traceback
xuất hiện ở **mọi** lần shutdown bình thường sẽ tập cho người vận hành thói
quen bỏ qua traceback — đúng lúc cần họ chú ý thì họ đã quen lướt qua.

## Việc cần làm

Sửa **chỉ** `trading/engine/main.py`, **chỉ** vùng dòng 143-145.

Sau khi `cancel()`, phải chờ task kết thúc và nuốt exception của nó (cả
`CancelledError` lẫn `ConnectionClosedError`) trước khi `break`.

### Ràng buộc

- **Không đổi hành vi huỷ.** Comment ở dòng 131-137 giải thích vì sao huỷ
  `next_msg` trước khi xử lý là AN TOÀN (chưa ack → JetStream giao lại, không
  mất không trùng). Giữ nguyên comment đó và giữ nguyên logic huỷ.
- Không đụng `finally: await nc.close()` (dòng 198-199).
- Không đụng `stop_task.cancel()` ở dòng 146 — nhánh đó không gây noise vì
  `Event.wait()` không ném exception khi bị huỷ ngoài `CancelledError`, và
  nó không bị đụng bởi `nc.close()`. Nếu bạn cho rằng nhánh đó CŨNG cần sửa,
  hãy chứng minh bằng log thật trước, đừng sửa phòng xa.
- Không đụng file nào khác. Không sửa `docker-compose.yml`.
- **Chạy `gitnexus_impact` trên `run` trước khi sửa** và báo blast radius.

## Kiểm chứng (dán output THẬT)

1. **Log sạch.** `docker compose up -d engine` → chờ nó lên → `docker compose
   stop engine` → `docker compose logs engine`.
   → **Kỳ vọng: 0 dòng chứa `Task exception was never retrieved`.**
   Dán số đếm thật (vd bằng cách grep/Select-String rồi đếm).

2. **Không hỏng thứ đã đạt.** Vẫn `ExitCode = 0` và thời gian thoát vẫn dưới
   2s. → Dán cả hai con số.

3. **Lặp 3 lần.** → Dán cả 3 bộ (số dòng noise, exit code, thời gian).

4. **Sức phân biệt (BẮT BUỘC).** Hoàn tác phần sửa, chạy lại một lần, xác nhận
   dòng noise **quay lại** (> 0). Khôi phục, xác nhận về 0.
   → Điều này chứng minh chính phần sửa của bạn tạo ra kết quả, không phải
   trùng hợp về timing. Noise này phụ thuộc thời điểm GC nên rất dễ "biến mất"
   một cách ngẫu nhiên — đó là lý do bước này bắt buộc.

5. `uv run pytest -q` (kỳ vọng 242 passed) + `uv run ruff check trading tests`.

## Không được làm

- Không commit, không push.
- Không chạy collector.
- Không "tiện thể" dọn warning nào khác trong log.
