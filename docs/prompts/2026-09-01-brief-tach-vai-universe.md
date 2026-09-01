# Brief 2026-09-01 (đợt 2) — Tách hai vai của `is_active`: mã đáng giao dịch ≠ mã bắt buộc phải có giá

Dành cho agent thực thi. Tự chứa. Quyết định của chủ dự án: **tách hai vai**.

---

## 1. Vấn đề — đo được, không phải suy đoán

Lịch chạy backfill hằng đêm (`trading-backfill-universe`, 20:30 T2–T6) **đã cài
và đã chạy, nhưng chạy 0 mã**:

```
logs/backfill.log:
2026-09-01 07:29:42 backfill start
[load] 0 ma tu universe (is_active)
DONE: ok=0 skip=0 err=0 / 0
```

Vì `symbol_universe` có **1.595 mã nhưng 0 mã `is_active = true`**
(`SELECT count(*) FILTER (WHERE is_active) FROM symbol_universe;` → 0).
`scripts/screen_liquidity.py` (Task 6) là thứ set cờ đó, và chưa từng chạy thật.

Nhưng chỉ chạy nó là chưa đủ. Đo thanh khoản 20 phiên gần nhất của đúng những
mã hệ thống phụ thuộc:

| Mã | tỷ VND/phiên | Vai trò |
|---|---|---|
| SSI | 432,15 | đang **nắm giữ** (0434226) |
| VCB | 259,72 | đang **nắm giữ** |
| HCM | 116,26 | đang **nắm giữ** |
| TCX | 72,90 | đang **nắm giữ** |
| IJC | 15,70 | `config.symbols` — engine giao dịch |
| AAA | 8,77 | `config.symbols` |
| HII | 7,00 | `config.symbols` |
| FOX | 4,13 | đang **nắm giữ** |
| **CAP** | **0,63** | đang **nắm giữ** |

Ngưỡng ≥1 tỷ loại mất **CAP**; ngưỡng ≥5 tỷ loại thêm **FOX**. Cả hai là cổ
phiếu thật trong tài khoản. Mất bar hằng ngày của chúng thì sau 5 phiên NAV
tính chúng bằng 0 (`account_sync.py:120-149`, fail-safe "giá cũ > 5 phiên ⇒
tính 0 + WARN"), mà NAV giờ là **số nhân kích thước lệnh thật** (commit `6159d39`).

**Gốc vấn đề:** một cờ `is_active` đang gánh hai câu hỏi khác nhau —
*"mã nào đáng giao dịch?"* (lọc thanh khoản) và *"mã nào bắt buộc phải có giá
hằng ngày?"* (mã đang nắm giữ + mã engine giao dịch). Trộn hai cái vào một cờ
thì hễ siết ngưỡng là âm thầm mất giá của mã đang cầm.

**Việc của bạn: tách hai vai đó ra.** Giữ `is_active` đúng nghĩa thanh khoản;
thêm một tập "bắt buộc phải có giá"; backfill và kiểm tra dữ liệu chạy trên
**hợp** của hai tập.

---

## 2. Môi trường

- Windows 11, có PowerShell và Git Bash. Repo:
  `D:\My_Vault_Obsidian\Project\AI_auto_trading_system`.
- Docker compose đang chạy. Truy vấn nhanh:
  `docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "..."`
- **`DB_DSN` phải dùng `127.0.0.1`, KHÔNG `localhost`** — trên máy này `localhost`
  ra IPv6 trước, treo ~30 giây mỗi lần kết nối.
- Script không tự đọc `.env`: `set -a && . ./.env && set +a` (Git Bash).
- Lệnh quá 10 phút bị cắt — việc dài chạy tách rời.
- Không in giá trị secret ra bất cứ đâu.

---

## 3. Phạm vi phẫu thuật

**Được sửa:** `trading/storage/db.py`, `scripts/backfill_universe.py`,
`scripts/daily_data_check.py`, `tests/test_storage.py`,
`tests/test_backfill_universe.py`, `tests/test_data_quality.py`.

**KHÔNG được đụng:** `trading/engine/*`, `trading/real_orders.py`,
`trading/risk.py`, `config/config.yaml`, `scripts/heartbeat_check.py`,
`scripts/screen_liquidity.py` (chỉ *chạy*, không sửa), và các scheduled task
đã cài (lệnh của chúng dùng `--use-universe`, không cần đổi).

---

## 4. Các bước

### Bước 1 — `Storage.read_must_price_symbols()`

Thêm vào `trading/storage/db.py`:

```
def read_must_price_symbols(self, accounts: list[str], extra: list[str]) -> list[str]
```

Trả về danh sách đã sắp xếp, không trùng, gồm: `extra` (sẽ truyền `cfg.symbols`)
hợp với mã đang nắm giữ của **từng** tài khoản trong `accounts`.

**Bắt buộc dùng lại `self.read_real_positions(account)`** để lấy mã đang nắm —
**không** viết truy vấn `account_position_snapshot` mới. Hàm đó đã xử lý đúng
hai chuyện tinh vi mà truy vấn thô sẽ làm sai: nó bám mốc `account_sync_log`
(phân biệt "chưa đồng bộ bao giờ" với "đã đồng bộ và rỗng"), và nó chỉ trả mã
có `quantity > 0`. Viết lại là tái lập đúng lỗi đã sửa (bài học `4ea4c8d`:
một công thức hai bản).

→ **Kiểm chứng** (`tests/test_storage.py`): seed vị thế cho 2 tài khoản khác
nhau + `extra=['HII']`; khẳng định (a) kết quả là hợp của cả ba nguồn, (b)
không trùng lặp, (c) mã có `quantity = 0` **không** xuất hiện, (d) tài khoản
chưa từng đồng bộ không làm hàm nổ.

### Bước 2 — Backfill chạy trên hợp hai tập

Trong `scripts/backfill_universe.py`, nhánh `--use-universe` (dòng ~201): thay
vì chỉ `read_active_universe()`, lấy hợp với `read_must_price_symbols(...)`.
`cfg.ssi_equity_accounts` và `cfg.symbols` đã có sẵn trong `cfg`.

In ra dòng log **phân tách rõ hai nguồn**, ví dụ:
`[load] 174 ma thanh khoan + 6 ma bat buoc co gia (2 ngoai universe) = 178 ma`
— để lần sau nhìn log là biết ngay tập nào rỗng.

→ **Kiểm chứng** (`tests/test_backfill_universe.py`): `is_active` chỉ có
`{VCB, SSI}`, mã nắm giữ có `CAP`, `cfg.symbols` có `HII` ⇒ danh sách trả về
phải chứa **cả CAP lẫn HII**. Đây là bất biến trung tâm của cả brief: **một mã
đang nắm giữ nhưng KHÔNG đủ thanh khoản vẫn phải được nạp.**

### Bước 3 — `daily_data_check` kiểm trên cùng tập

`scripts/daily_data_check.py:114` cũng đang dùng `read_active_universe()`. Đổi
sang cùng hợp như bước 2.

Lý do bắt buộc phải đổi cả hai: nếu backfill nạp CAP mà kiểm tra không soi CAP,
thì ngày CAP thiếu bar sẽ không ai biết — đúng kiểu hỏng âm thầm mà cả đợt này
sinh ra để diệt.

→ **Kiểm chứng:** test cho thấy mã nắm giữ thiếu bar thì `evaluate_daily_completeness`
báo thiếu (trước khi sửa thì không).

### Bước 4 — Chạy `screen_liquidity.py` để set `is_active`

**Ngưỡng: 5 tỷ VND/phiên** (→ 174 mã). Chọn ngưỡng chặt được vì bước 1–3 đã bảo
đảm mã nắm giữ luôn được nạp bất kể thanh khoản.

Chạy `--dry-run` trước để đối chiếu con số, rồi chạy thật.

→ **Kiểm chứng:** `SELECT count(*) FILTER (WHERE is_active) FROM symbol_universe;`
ra ~174; và `CAP` phải **`is_active = false`** — đúng như thiết kế, nó được nạp
qua đường "bắt buộc có giá" chứ không phải đường thanh khoản.

### Bước 5 — Chạy thật scheduled task, xem log

Chạy tay `schtasks /run /tn trading-backfill-universe`, chờ xong, đọc
`logs/backfill.log`.

→ **Kiểm chứng:** dòng `[load]` cho số mã **> 0**, và `DONE: ok=... err=0`.
Dán nguyên văn. Nếu `err > 0` thì nói rõ mã nào lỗi và vì sao — **đừng giấu
trong tổng số**.
→ *Lưu ý đã biết:* mã đang nắm giữ có thể **không nằm trong `symbol_universe`**
(chứng quyền bị `load_symbols` lọc bỏ vì `cw_underlying_symbol` khác null).
Một mã lỗi **không được giết cả job** — `backfill_universe` đã có try/except
từng mã, giữ nguyên hành vi đó.

### Bước 6 — Sabotage (bắt buộc)

Đổi phép **hợp** thành phép **giao** ở bước 2 ⇒ test bước 2 phải ĐỎ.
Khôi phục, chạy lại cho xanh. **Dán nguyên văn output đỏ.**

---

## 5. Cấm

- Không commit, không push — Claude audit rồi commit.
- Không bật `real_trading_enabled`, không sửa `config/config.yaml`.
- Không gọi API đặt/huỷ lệnh SSI. Backfill chỉ gọi API dữ liệu.
- Không `TRUNCATE`, không `DROP`, không xoá dòng nào. `bars_daily` là hypertable —
  `pg_dump --data-only` trên nó cho file RỖNG 486 byte, đừng tin bản sao lưu
  kiểu đó.
- Phát hiện vấn đề ngoài phạm vi: **báo cáo**, không tự sửa.

## 6. Tiêu chí hoàn thành

- `uv run pytest -m "not integration" -q` xanh (hiện tại: 328 passed).
- `uv run ruff check trading tests scripts` sạch.
- Output sabotage dán nguyên văn.
- `logs/backfill.log` cho thấy job chạy với số mã > 0, kèm dòng `[load]` phân
  tách hai nguồn.
- Việc nào không làm được thì nói rõ vì sao. Không đoán, không tóm tắt bằng
  chứng thành chữ "pass".
