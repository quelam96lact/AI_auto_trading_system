# Brief đợt 189: sửa NAV tài khoản thật — cộng giá trị lệnh mua đã trừ tiền nhưng cổ phiếu chưa vào `quantity`

- Người lập: Claude (planner), 23/10/2026. Agent thực thi: viết code + test, **không commit, không push**.
- Liên quan: memory `nav-thieu-co-phieu-cho-ve-t2`; đợt 167 (lưu trường `buy_t*` và `bought_quantity`).
- Đây là sửa lỗi kỹ thuật, không phải phép đo chiến lược, nên không cần dòng H trong spec.

## 0. Lỗi là gì (Claude đã đo trên DB, chỉ đọc, ngày 23/10)

Hiện tại:

```
NAV = withdrawable − total_debt + Σ(quantity × giá)
```

Code ở `_sync_nav` (`trading/collector/account_sync.py`) và `Storage.compute_nav` (`trading/storage/db.py`).

Khi lệnh mua khớp (ngày T0), SSI trừ tiền ngay (hoặc ghi nợ margin). Nhưng cổ phiếu chỉ vào `quantity` vào **đêm T+1**. Trong khoảng hơn một ngày đó, NAV **thiếu đúng số tiền của lệnh mua**.

Lần mua 100 TCX của tài khoản 0434226, chủ dự án đã xác nhận (giờ VN):

| Thời điểm | `quantity` TCX | `bought_quantity` | `withdrawable` | `buy_t0` | `buy_t1` | `buy_t2` | NAV đang ghi |
|---|---|---|---|---|---|---|---|
| 12/10 13:03 (trước khớp) | 68 | 0 | 9.595.541 | 0 | 0 | 0 | 202.519.681 |
| 12/10 13:13 (khớp) | 68 | 100 | 6.848.691 | 2.746.850 | 0 | 0 | 199.772.831 |
| 13/10 07:32 (sáng T+1) | 68 | **0** | 6.848.658 | 0 | 2.746.850 | 0 | 199.772.798 |
| 13/10 22:26 | 68 | 0 | 6.848.625 | 0 | 0 | 2.746.850 | 198.008.665 |
| 13/10 22:31 (cổ phiếu vào) | 168 | 0 | 6.848.625 | 0 | 0 | 2.746.850 | 200.718.665 |

Đọc bảng:
- Lúc 13:13, NAV đang ghi cộng `buy_t0` ra 199.772.831 + 2.746.850 = **202.519.681**, khớp từng đồng với NAV trước khớp.
- Sáng T+1, `bought_quantity` đã về 0 nhưng cổ phiếu vẫn chưa vào `quantity`. Khoản tiền nằm ở `buy_t1`. **Cộng `bought_quantity × giá` là cách sửa sai**, vì nó bỏ sót cả ngày T+1.
- Lúc `buy_t1` chuyển sang `buy_t2`, cổ phiếu vào `quantity` cùng lúc hoặc vài phút sau. Vì vậy **không được cộng `buy_t2`**, nếu không sẽ tính trùng.

Lần mua 800 TCX (khoảng 15/10) theo đúng mẫu này:
- 16/10 07:37: `buy_t1` = 22.315.650, `quantity` vẫn 168. NAV đang ghi là 178,4 triệu, thiếu 22,3 triệu.
- 17/10 00:45: `buy_t2` = 22.315.650 và `quantity` 968 xuất hiện trong cùng một snapshot.

**Chiều bán không sửa trong đợt này.** Lần bán 300 VCB (khoảng 15/10) cho thấy:
- Sáng T+1: VCB vẫn nằm trong `quantity`, nên NAV định giá theo giá thị trường, đúng.
- Đêm T+1: VCB rời `quantity`, tiền bán trả nợ margin. Phần dư 1,51 triệu nằm ở `account_balance` nhưng `withdrawable` vẫn là 0 cho tới T+2.

NAV vì vậy thiếu khoảng 1,5 triệu trong 2 ngày. Lệch nhỏ và về phía an toàn. Mới có một lần bán nên chưa đủ căn cứ để sửa.

## 1. Cách sửa (đã chốt)

```
NAV = withdrawable − total_debt + Σ(quantity × giá) + buy_t0 + buy_t1
```

- `buy_t0`, `buy_t1` lấy từ **cùng một dòng** `account_balance_snapshot` với `withdrawable` và `total_debt` (dòng mới nhất). Đọc bằng một câu SQL, không đọc hai lần.
- Tính theo giá vốn (số tiền SSI đã trừ), không theo giá thị trường. Lệch tối đa khoảng một phiên biến động trên một lệnh, chấp nhận được.
- **Không cộng `buy_t2`.**
- **Không cộng** `bought_quantity × giá`, `sell_t*`, `advanced_cash_*`, `dividend_cash` hay `dividend_quantity`.

**Giả định đã nêu:**
- Thứ tự quan sát được ở cả hai lần mua là `buy_t1` sang `buy_t2` trước hoặc cùng lúc cổ phiếu vào `quantity`. Nếu SSI có lần đảo thứ tự, NAV sẽ cao hơn thực tế một khoản bằng lệnh mua, trong vài phút lúc khoảng 22h–01h. Lúc đó engine không đặt lệnh nên chấp nhận được.
- Engine đặt lệnh ban ngày, đọc NAV ở `account_nav_snapshot`. Sau khi sửa, NAV trong ngày T0/T+1 sẽ **cao hơn hiện tại** đúng bằng giá trị lệnh mua. Đó là giá trị đúng, nhưng là thay đổi theo hướng tăng cỡ lệnh, nên audit phải kiểm kỹ.

## 2. Phạm vi file

**Được sửa:**
- `trading/storage/db.py`:
  - `compute_nav`: thêm tham số keyword `pending_buy_cost: float = 0.0`, cộng thẳng vào NAV. Mặc định 0 nên mọi caller và test cũ giữ nguyên hành vi.
  - Thêm **method mới** `read_balance_for_nav(account_no) -> tuple[float, float, float, datetime] | None`, trả `(withdrawable, total_debt, buy_t0 + buy_t1, ts)` từ dòng mới nhất. Docstring ghi lý do và trỏ tới brief này.
- `trading/collector/account_sync.py`, hàm `_sync_nav`: đổi sang `read_balance_for_nav` và truyền `pending_buy_cost`. Cập nhật docstring công thức.
- Test: `tests/test_storage.py`, `tests/test_nav_vn_market_time.py`, `tests/test_account_sync.py` (chỉ thêm test, hoặc sửa fake storage cho có method mới).

**Không được đụng:**
- `read_account_balance_with_debt`. Hàm này còn được dùng ở CONFIRM-1 (`account_sync.py` khoảng dòng 120), nên giữ nguyên.
- `trading/engine/*` và `trading/real_orders.py`.
- `trading/storage/schema.sql`: các cột đã có từ đợt 167.
- `_sync_positions`, `read_real_positions`, và mọi thứ ở chiều bán.

**Thêm các ràng buộc:**
- Không ghi, sửa hay xoá dữ liệu DB thật. Không tính lại `account_nav_snapshot` cũ.
- Không restart container, không chạy `scripts/sched.sh`, không gọi API SSI hay DNSE thật.
- Không mở `.env` hay `.ssi_sdk_token.json`.
- Thấy vấn đề ngoài phạm vi thì ghi vào báo cáo, không tự sửa.

## 3. GitNexus (bắt buộc)
- **Trước khi sửa:** chạy `node .gitnexus/run.cjs impact "compute_nav" --direction upstream --repo .`, rồi làm tương tự cho `_sync_nav`. Chạy `context` cho `read_account_balance_with_debt` để xác nhận không đụng tới nó. Dùng `gitnexus` hoặc `node .gitnexus/run.cjs`, **không dùng npx**.
- Nếu ra HIGH/CRITICAL thì báo trong báo cáo. UNKNOWN thì grep xác nhận.
- **Sau khi sửa:** chạy `node .gitnexus/run.cjs detect-changes --scope all --repo .` và dán nguyên văn phần tóm tắt. Nếu ra `partial` hoặc `truncated` thì chạy lại.

## 4. Các bước (TDD)

1. **Test `compute_nav` (viết đỏ trước):**
   - Cùng đầu vào, có `pending_buy_cost=2_746_850` thì NAV lớn hơn đúng 2.746.850.
   - Không truyền thì NAV bằng kết quả cũ.
   - Mã không định giá được vẫn tính 0 và vẫn nằm trong `unpriced` khi có `pending_buy_cost`.

   → kiểm chứng: test mới đỏ trước khi sửa, xanh sau khi sửa; test `compute_nav` cũ không đổi một dòng nào mà vẫn xanh.

2. **Test `read_balance_for_nav`** (integration, gắn `@pytest.mark.integration`, chạy trên DB `trading_test` như các test storage khác):
   - Ghi hai dòng balance khác `ts`. Hàm phải trả dòng mới nhất, và phần thứ ba bằng `buy_t0 + buy_t1` của **chính dòng đó**.
   - `buy_t2` không được tính.

   → kiểm chứng: `uv run pytest tests/test_storage.py -k read_balance_for_nav -q` xanh (cần `docker compose --profile test up -d nats-test` và DB test).

3. **Test `_sync_nav` tái hiện vòng đời lệnh mua**, dùng fake storage theo kiểu `_captured_nav` trong `tests/test_nav_vn_market_time.py`. Ba trạng thái, cùng giá TCX 27.350 và cùng các vị thế khác:

   | Trạng thái | `quantity` TCX | `withdrawable` | `buy_t0` | `buy_t1` | `buy_t2` |
   |---|---|---|---|---|---|
   | (A) T0 sau khớp | 68 | W − 2.746.850 | 2.746.850 | 0 | 0 |
   | (B) sáng T+1 | 68 | W − 2.746.850 | 0 | 2.746.850 | 0 |
   | (C) sau cập nhật đêm | 168 | W − 2.746.850 | 0 | 0 | 2.746.850 |

   - NAV của (A) và (B) phải bằng **NAV trước khớp**: W, 68 TCX, không có `buy_*`.
   - NAV của (C) phải bằng NAV trước khớp cộng 100 × 27.350 − 2.746.850 (chênh giá/phí, khoảng −11.850).
   - Một test riêng: (C) **không được** lớn hơn NAV trước khớp cộng 100 × 27.350. Test này bắt lỗi tính trùng `buy_t2`.

   → kiểm chứng: 4 test mới xanh.

4. **Phép phá.** Mỗi phép phải làm ít nhất một test **gọi code sản phẩm** đỏ. Test chỉ so hằng số viết trong test thì không tính; đợt 188 đã mắc lỗi này. Phá xong khôi phục, rồi ghi lệnh và kết quả vào báo cáo.
   - (m1) bỏ `buy_t1`, chỉ cộng `buy_t0`: (B) phải đỏ.
   - (m2) cộng thêm `buy_t2`: (C) phải đỏ.
   - (m3) thay cả công thức bằng `bought_quantity × giá`: (B) phải đỏ.
   - (m4) `read_balance_for_nav` lấy `buy_*` từ dòng cũ hơn dòng `withdrawable`: test bước 2 phải đỏ.

   Không có cờ phá thử trong code sản phẩm.

5. **Toàn suite:**
   - `uv run pytest -m "not integration" -q`: không đỏ thêm so với trước khi bắt đầu. Ghi số passed trước và sau.
   - `uv run ruff check trading tests` sạch.

## 5. Báo cáo agent phải nộp
1. Nguyên văn kết quả GitNexus `impact`/`context` trước khi sửa và `detect-changes` sau khi sửa.
2. Diff tóm tắt theo file. Mọi dòng thay đổi phải truy ngược được về §2.
3. Danh sách test mới, số passed trước/sau, bảng phép phá (m1)–(m4) kèm kết quả.
4. Chỗ mơ hồ đã gặp. Nếu có lựa chọn ảnh hưởng hành vi mà brief chưa quy định, **dừng và hỏi**.
5. Cam kết: không ghi DB thật, không gọi API thật, không restart container, không commit/push.

## 6. Claude làm sau khi nhận báo cáo
1. **Audit:**
   - đối chiếu diff với §2;
   - chạy lại test và (m1)–(m4);
   - xác nhận `read_account_balance_with_debt` không đổi.
2. **Phát lại trên DB thật, chỉ đọc:** tính NAV theo công thức mới cho 0434226 từ 12/10 đến 20/10, từ các snapshot đã lưu. Kỳ vọng:
   - NAV lúc 12/10 13:13 và 13/10 07:32 bằng NAV trước khớp (±1.000 đồng);
   - bước nhảy 16/10 → 17/10 còn dưới 2 triệu (phần lệch chiều bán), thay vì khoảng 22 triệu như hiện tại.
3. Commit + push. Rebuild collector **sau 15:00**, ngoài giờ giao dịch. Theo dõi `account_nav_snapshot` qua một đêm có cập nhật SSI.
4. Cập nhật memory `nav-thieu-co-phieu-cho-ve-t2`. Mở việc theo dõi chiều bán: đủ ≥ 2 lần bán nữa thì mới quyết có sửa hay không.
