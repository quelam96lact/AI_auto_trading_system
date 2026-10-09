# Brief đợt 167, vòng 2 — Lưu các khoản tiền chờ thanh toán của SSI vào `account_balance_snapshot` (CHƯA sửa NAV)

Ngày: 09/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.

## 0. Vì sao

Vòng 1 (`e356ec6`) đã lưu các trường số lượng chờ về/chờ đi của vị thế. Thăm dò chỉ đọc của vòng 1 (09/10, tài khoản `0434226`) cho thấy nửa còn lại nằm trong dict `equity` của phản hồi số dư `EP_ACCOUNT_BALANCE`, và hệ thống đang bỏ:

```
advancedCashT0: '0'   advancedCashT1: '0'
buyT0: '0'            buyT1: '0'            buyT2: '23979800'
sellT0: '0'           sellT1: '0'           sellT2: '0'
dividend: '0'
```

`buyT2 = 23.979.800` khớp tiền mua 400 CTD đang chờ thanh toán. Muốn đối chiếu NAV với giao dịch thật thì phải có các trường này **từ cùng lúc** với các trường vị thế. Vì vậy hai vòng triển khai cùng một lần, sau 15:00 hôm nay. Brief vòng 1 lẽ ra phải gồm phần này; đó là thiếu sót của Claude.

## 1. Việc làm
1. Thêm 9 cột vào `account_balance_snapshot`: `buy_t0`, `buy_t1`, `buy_t2`, `sell_t0`, `sell_t1`, `sell_t2`, `advanced_cash_t0`, `advanced_cash_t1`, `dividend_cash`.
   - Dạng `double precision NOT NULL DEFAULT 0` (cùng kiểu với các cột tiền hiện có).
   - Thêm vào `CREATE TABLE` **và** bằng `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, đúng khuôn vòng 1 đã dùng cho `account_position_snapshot` (`trading/storage/schema.sql`).
   - `dividend_cash` lấy từ key `dividend`. Tên cột khác để không nhầm với `dividend_quantity` của vị thế.
2. `Storage.save_account_balance`: thêm 9 tham số **có mặc định 0.0** (để mọi chỗ gọi cũ vẫn chạy), ghi vào INSERT và `ON CONFLICT ... DO UPDATE`.
3. `_sync_balance` (`trading/collector/account_sync.py`, lời gọi `storage.save_account_balance`): đọc 9 key từ `equity` theo đúng cách `buyUnmatched` đang được đọc, tức `float(equity.get("buyT2") or 0)`.
4. **Không đổi gì khác:** CONFIRM-1, `_find_missing_balance_fields` và `REQUIRED_BALANCE_FIELDS`, `read_account_balance_with_debt`, `compute_nav`, `_sync_nav`, đường lệnh thật giữ nguyên hành vi. Thiếu một trong 9 key mới **không** được làm bỏ qua cả nhịp; ghi 0.

## 2. Phạm vi
- **Được sửa:** `trading/storage/schema.sql` (chỉ thêm cột), `trading/storage/db.py` (chỉ `save_account_balance`), `trading/collector/account_sync.py` (chỉ lời gọi `save_account_balance` trong `_sync_balance`), `tests/test_account_sync.py`, `tests/test_storage.py`.
- **Không sửa:** mọi file khác. Không build hay khởi động lại container. Không chạy ALTER trên DB thật. Không gọi API SSI lần nữa (dùng output thăm dò ở §0).
- GitNexus: chạy `npx gitnexus analyze` trước. Chạy `impact` cho `_sync_balance` và `save_account_balance`, dán mức rủi ro. Chạy `detect_changes` sau khi xong.

## 3. Kiểm chứng (TDD, thấy đỏ rồi mới viết code)
1. `_sync_balance` với `equity` giả chứa đúng các giá trị ở §0 (cộng ba trường bắt buộc khác 0) → `save_account_balance` nhận `buy_t2=23979800.0`, các trường khác đúng giá trị.
2. `equity` giả **thiếu** cả 9 key mới → vẫn ghi, 9 trường = 0.0, không cảnh báo mới.
3. Test DB (integration, `trading_test`): ghi rồi đọc lại một dòng có 9 trường khác 0 → đúng giá trị. Ghi đè cùng `(account_no, ts)` → giá trị mới.
4. `init_schema` chạy hai lần không lỗi; dòng cũ đọc ra 0.
5. Mọi test hiện có của `account_sync`, CONFIRM-1 và `compute_nav` xanh mà không sửa kỳ vọng nào, trừ chỗ so khớp nguyên văn tham số gọi `save_account_balance` (nếu có). Liệt kê từng test phải sửa, kèm lý do.

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Đọc `buyT2` thành `buyT1` → test 1 đỏ.
- Bỏ các cột mới khỏi `ON CONFLICT ... DO UPDATE` → test 3 đỏ (phần ghi đè).
- Cho thiếu key thì `return` sớm → test 2 đỏ.

```
uv run pytest tests/test_account_sync.py tests/test_storage.py -v
docker compose --profile test up -d nats-test
uv run pytest -q
uv run ruff check trading tests scripts
```

**Hoàn thành khi:**
- Test mới xanh, ba bước phá hoại mỗi bước làm đỏ đúng test đã nêu.
- Bộ đầy đủ không có test mới đỏ. Mốc 09/10: `1922 passed`; dán số trước và sau.
- ruff sạch.
- `detect_changes` chỉ gồm các file ở §2, cộng dòng thống kê GitNexus nếu `analyze` tự sửa `AGENTS.md`/`CLAUDE.md`.

## 4. Báo cáo cho Claude
1. Kết quả `impact` kèm mức rủi ro.
2. Output pytest/ruff, bảng phá hoại, danh sách test cũ phải sửa.
3. Output `detect_changes`.
4. Mọi chỗ phải tự diễn giải; không im lặng chọn.
