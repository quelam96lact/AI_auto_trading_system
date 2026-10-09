# Brief đợt 167 — Lưu các trường "cổ phiếu đang chờ về / chờ đi" của SSI, để đo NAV sai bao nhiêu (CHƯA sửa công thức NAV)

Ngày: 09/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.

## 0. Vấn đề (Claude đã đo trên DB thật sáng 09/10)

NAV tài khoản thật `0434226` qua đêm 08→09/10 dao động từ **179,2 triệu lên 204,1 triệu**, trong khi ngoài giờ giao dịch giá và danh mục không đổi. Lần theo `account_position_snapshot` và `account_balance_snapshot`:

| Thời điểm (giờ VN) | Danh mục CTD | Tiền / nợ |
|---|---|---|
| 05/10 13:57 | CTD xuất hiện với `quantity = 0` | số dư giảm khoảng 29 triệu ngay lúc đó |
| 07/10 07:50 | 500 | |
| 07/10 11:03 | | số dư giảm khoảng 24 triệu (≈ 400 CTD × 59 nghìn) |
| 08/10 07:47 | 800 | |
| 08/10 22:45 | **1.200** (sau đợt bảo trì SSI) | gần như không đổi |

Giá CTD trong `bars_daily` không có cú giảm nào, nên đây **không phải cổ phiếu thưởng**. Giả thuyết của Claude (CHƯA kiểm): **tiền bị trừ ngay lúc khớp mua, còn `quantity` chỉ tăng khi cổ phiếu về (T+2)**. Trong khoảng đó NAV thấp hơn thực tế đúng bằng giá trị cổ phiếu đang chờ về. Lần nhảy 22:45 là +24,9 triệu, tức khoảng 14% NAV.

Code hiện tại (`trading/collector/account_sync.py`, `_sync_positions` và `_sync_nav`): NAV = `withdrawable − total_debt + Σ quantity × giá`. SDK SSI (`ssi_sdk/models/portfolio.py:202`, `EquityPosition`) trả thêm `bought_quantity`, `buying_quantity`, `sold_quantity`, `selling_quantity`, `t1_sell_quantity`, `t2_sell_quantity`, `dividend_quantity`, `block_quantity`, `mortgage_quantity`, `restricted_quantity`. Hệ thống **bỏ hết**, chỉ lưu `quantity`, `cost_price`, `sellable_quantity`.

**Chưa biết, nên brief này KHÔNG sửa công thức NAV:** nghĩa chính xác của từng trường, khi nào tăng, khi nào về 0; `withdrawable` đã trừ tiền mua chưa thanh toán hay chưa; tiền bán chờ về (T+2) nằm ở đâu. Sửa NAV khi chưa biết thì có thể đổi lỗi "NAV thấp" thành lỗi "NAV cao", và lỗi cao nguy hiểm hơn vì đường lệnh thật dùng NAV để tính khối lượng. Hiện lỗi đang nghiêng về phía **an toàn** (NAV thấp → lệnh nhỏ hơn).

## 1. Việc làm

1. **Thăm dò chỉ đọc, một lần, không ghi file nào vào repo:** gọi API SSI qua đường xác thực có sẵn của repo (xem `trading/collector/account_sync.py:sync_account_data`, `ensure_authenticated`), cho tài khoản `0434226`.
   - In **mọi** trường của từng `EquityPosition`.
   - In **mọi key và value** của dict `equity` trong phản hồi số dư `EP_ACCOUNT_BALANCE` (không chỉ ba trường đang dùng).
   - Không gọi API đặt lệnh hay API nào có tác dụng ghi. Không in token hay khóa.
   → **kiểm chứng bằng:** dán nguyên output vào báo cáo cho Claude, chỉ trong chat.
2. **Lưu các trường số lượng còn thiếu vào `account_position_snapshot`:** `bought_quantity`, `buying_quantity`, `sold_quantity`, `selling_quantity`, `t1_sell_quantity`, `t2_sell_quantity`, `dividend_quantity`.
   - Dạng `integer NOT NULL DEFAULT 0`, thêm bằng `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` trong `trading/storage/schema.sql`, theo đúng khuôn có sẵn (dòng 279).
   - `_sync_positions` đưa các trường này vào dict; `Storage.save_account_positions` ghi chúng, kể cả trong `ON CONFLICT ... DO UPDATE`.
   → **kiểm chứng bằng:** test ở mục 3.
3. **Không đổi gì khác:** `compute_nav`, `_sync_nav`, `read_real_positions`, đường lệnh thật, CONFIRM-1 giữ nguyên hành vi. Danh mục rỗng vẫn ghi như cũ.

## 2. Phạm vi
- **Được sửa:** `trading/storage/schema.sql` (chỉ thêm cột), `trading/storage/db.py` (chỉ `save_account_positions`), `trading/collector/account_sync.py` (chỉ phần dựng `rows` trong `_sync_positions`), `tests/test_account_sync.py` và test DB tương ứng của `save_account_positions` (tìm file test hiện có, không tạo file mới nếu đã có chỗ).
- **Không sửa:** mọi hàm đọc vị thế, mọi công thức NAV, engine, `real_orders.py`, script, file khác.
- **Không** build lại hay khởi động lại container; Claude triển khai ngoài giờ phiên. **Không** chạy ALTER trên DB thật; cột chỉ được thêm khi collector khởi động lại và gọi `init_schema`.
- GitNexus: chỉ mục đang cũ, chạy `npx gitnexus analyze` trước. Chạy `impact` cho `_sync_positions` và `save_account_positions`, dán mức rủi ro. Chạy `detect_changes` sau khi xong.

## 3. Kiểm chứng (TDD, thấy đỏ rồi mới viết code)
1. `_sync_positions` với một `EquityPosition` giả có `bought_quantity=400`, `t2_sell_quantity=100`, v.v. → dict gửi xuống `save_account_positions` chứa đúng 7 trường với đúng giá trị.
2. Test DB (integration, trên `trading_test`): ghi rồi đọc lại một dòng có 7 trường khác 0 → đúng giá trị. Ghi đè cùng `(account_no, ts, symbol)` → giá trị mới.
3. `init_schema` chạy hai lần liên tiếp không lỗi (idempotent), và dòng cũ không có cột mới thì đọc ra 0.
4. **Hành vi cũ không đổi:** mọi test hiện có của `account_sync`, `compute_nav`, `read_real_positions` xanh mà không sửa kỳ vọng nào.

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Bỏ `bought_quantity` khỏi dict trong `_sync_positions` → test 1 đỏ.
- Bỏ các cột mới khỏi `ON CONFLICT ... DO UPDATE` → test 2 đỏ (phần ghi đè).
- Bỏ `IF NOT EXISTS` → test 3 đỏ.

```
uv run pytest tests/test_account_sync.py -v
docker compose --profile test up -d nats-test
uv run pytest -q
uv run ruff check trading tests scripts
```

**Hoàn thành khi:**
- 3 test mới xanh, ba bước phá hoại mỗi bước làm đỏ đúng test đã nêu.
- Bộ đầy đủ không có test mới đỏ. Mốc 09/10: `1919 passed`; dán số trước và sau.
- ruff sạch.
- `detect_changes` chỉ gồm các file ở §2, cộng các dòng thống kê GitNexus nếu `analyze` tự sửa `AGENTS.md`/`CLAUDE.md`.

## 4. Báo cáo cho Claude
1. Output thăm dò ở §1 bước 1, nguyên văn.
2. Kết quả `impact` kèm mức rủi ro.
3. Output pytest/ruff và bảng phá hoại.
4. Output `detect_changes`.
5. Mọi chỗ phải tự diễn giải; không im lặng chọn.

## 5. Bước sau (Claude, chưa giao)
- Triển khai sau 15:00; thu dữ liệu ít nhất 3 phiên có giao dịch mua và bán thật.
- Đối chiếu từng trường với giao dịch thật (chủ dự án xác nhận ngày, mã, khối lượng), rồi mới soạn brief sửa công thức NAV.
