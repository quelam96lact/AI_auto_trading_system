# Brief đợt 184 — Mở cổng đo order flow crypto từ 12/10 (chủ dự án cho phép)

Ngày: 11/10/2026. Người giao, audit, commit, push, **chạy phép đo**: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push, KHÔNG chạy phép đo**.
Nền: commit `b430199` (đợt 183b đã audit).

## 0. Yêu cầu và cách hiểu

**Chủ dự án (11/10):** "áp dụng order flow trong tháng 10".

**Crypto (đợt 183/183b):**
- Cổng ngày 01/11 chỉ để giữ ngân sách mục F, không bảo vệ dữ liệu nào. Dữ liệu dừng ở 2026-08 và đã niêm phong; đo ngày nào cũng ra cùng số.
- Chủ dự án cho phép dùng **giả thuyết thứ 10 của tháng 10**, vượt ngân sách. Claude ghi vào spec H trước khi chạy.
- Thiết kế đo **giữ nguyên toàn bộ** brief 183 §1 và brief 183b §1. Đợt này chỉ đổi ngày mở cổng.

**VN30F (đợt 162/182) không làm trong tháng 10:**
- Phép đo cần ≥ 40 phiên IS hợp lệ do máy ghi sổ lệnh tự thu từ 25/09; hiện mới khoảng 12 phiên.
- Cổng 01/12 là điều kiện dữ liệu, không phải luật ngân sách. **Không đổi.**

**Giao dịch thật:**
- Brief 183 đã chốt: "không có đường tới lệnh thật". Đợt này giữ nguyên.
- Nếu có cặp ĐẠT, bước sau là một brief riêng: chạy giấy trên dữ liệu trực tiếp và kiểm độ lệch Binance/BingX (183 §1.4). Brief đó chỉ được viết **sau** khi có kết quả.

## 1. Việc agent làm

1. Trong `scripts/screen_crypto_orderflow.py`: đổi `HOLDOUT_START_DATE` từ `date(2026, 11, 1)` thành `date(2026, 10, 12)`.
   - Thêm chú thích một dòng: `# Mo som theo cho phep cua chu du an 11/10 (gia thuyet 10 thang 10, spec H)`.
   - **Không** sửa dòng nào khác trong file.
2. Trong `tests/test_screen_crypto_orderflow.py`, chỉ sửa test 7:
   - 2026-10-11 ⇒ `return 2`, pipeline (mock) không được gọi;
   - 2026-10-12 ⇒ đi tiếp.
3. Sửa đúng hai dòng docstring hoặc chuỗi in có ghi "2026-11-01" hoặc "01/11" trong file trên cho khớp ngày mới, nếu có. Không đổi chữ nào khác.

**Phải giữ nguyên, không xoá, không làm yếu:**
- `crypto_block_end_fn` suy từ `block_id`;
- loader giữ nến trống với `close=None`;
- toàn bộ test 1–17, gồm 10, 11, 12 do Claude viết.

Agent phải dán `grep -c "^def test" tests/test_screen_crypto_orderflow.py tests/test_build_crypto_footprint.py`, trước và sau, để chứng minh số test không giảm.

**Không** chạy `scripts/screen_crypto_orderflow.py` với ngày ≥ 12/10, và **không** gọi `main()` trên `data/crypto_footprint_v2/` thật. Phép đo do Claude chạy sau khi audit.

## 2. Phép phá bắt buộc
| Phép phá | Test phải đỏ |
|---|---|
| (xv) cổng dùng `<=` thay vì `<` | 7 |

Sao lưu ngoài repo, khôi phục bằng `cp`, so `sha256`. Cấm `git checkout/restore/stash`.

## 3. Cổng kiểm cuối
- GitNexus (`node .gitnexus/run.cjs …`, không `npx`): `impact` upstream cho `main` của `screen_crypto_orderflow` trước khi sửa; `detect-changes --scope all` sau khi sửa.
- `uv run pytest -m "not integration" -q` trước và sau. `uv run ruff check trading tests scripts` sạch.
- Hôm nay (11/10), `uv run python scripts/screen_crypto_orderflow.py` vẫn trả 2. Dán output.

## 4. Bất biến
- **Không:** commit, push, ghi DB, đặt lệnh, gọi API BingX, chạy `scripts/sched.sh` hay script drill.
- **Không đọc:** `.ssi_sdk_token.json`, `.env`, `data/orderbook/`.

## 5. Sau khi audit (Claude làm, không phải agent)
1. Commit, push.
2. Chạy phép đo **một lần**, ngày 12/10 trở đi: `uv run python scripts/screen_crypto_orderflow.py`. Lưu nguyên văn output vào `docs/research/2026-10-dot-184-ket-qua-order-flow-crypto.md`.
3. Phán quyết theo đúng quy tắc 183 §1.4. **Không** đảo chiều, **không** đổi H, **không** đổi ngưỡng sau khi thấy số.
4. Dự đoán ghi trước (183 §1.5): **không cặp nào ĐẠT**.

## 6. Báo cáo cho Claude
- pytest trước/sau, ruff, output cổng ngày, số test trước/sau.
- Phép phá (xv), `impact`, `detect-changes`.
- Mục "brief mơ hồ ở đâu".
- Câu chốt: *"Tôi chưa chạy phép đo trên dữ liệu thật."*
