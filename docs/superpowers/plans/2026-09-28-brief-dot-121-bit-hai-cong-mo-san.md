# Brief đợt 121 — bịt hai cổng mở sẵn: giá 0 thành giá thật trên đường tiền thật, và mốc niêm phong crypto tuỳ chọn

**Base commit:** `6b09e9d` (cộng một commit đính chính báo cáo đi kèm brief này).
**Người thực thi:** agent. **Người audit + commit + push:** Claude.
**Báo cáo nền:** `docs/superpowers/research/2026-09-28-bao-tri-xoa-nen-gia-0-va-rebuild.md` §6.

---

## §0. Vì sao đợt này chen lên trước đợt trả nợ kỹ thuật

Tôi đã nói thứ tự là: (1) trả nợ kỹ thuật `screen_vcp_daily.py`, (2) đo lại SEPA với mốc trung tính. **Đổi lại:** tối 28/09 khi tự soát tôi tìm ra hai lỗ thuộc lớp "mặc-định-sai-an-toàn", một trong đó nằm trên **đường tiền thật** và làm **tắt im lặng** một cổng an toàn. Một lỗ đường tiền thật đứng trên một đợt refactor. Đợt trả nợ kỹ thuật vẫn là đợt kế tiếp, không bị bỏ.

Cả hai lỗ đều **không** làm sai kết luận nào đã có, và phơi nhiễm hôm nay bằng 0. Đây là bịt cổng trước khi có thiệt hại, không phải chữa thiệt hại.

---

## §1. Hai đính chính của tôi mà brief này dựa lên — đọc trước khi làm

### §1.1. GUARD-1 **bị tắt im lặng**, không phải báo động sai

Trong báo cáo nền §6.2 tôi viết rằng `read_last_close` nhận giá 0 thì hướng hậu quả là *ồn* (một CRITICAL sai). **Sai.** `trading/engine/main.py:471-480`:

```python
close = storage.read_last_close(sym)
if close is not None and (cheapest is None or close < cheapest):
    cheapest = close
if cheapest is not None and order_cap < cheapest * 100:
    alert("CRITICAL", "duong dat lenh that INERT: ...")
```

Một mã có `close = 0` trở thành `cheapest`, nên điều kiện thành `order_cap < 0` — **luôn sai**, không bao giờ báo. Một mã giá 0 trong `cfg.symbols` là đủ để **vô hiệu hoá toàn bộ** cổng vốn được dựng để hô lên khi đường đặt lệnh thật đã inert. Đây là im lặng, lớp lỗi nặng hơn hẳn nhiễu.

### §1.2. KHÔNG chặn giá 0 ở đường GHI nến ngày — tôi đã đề nghị sai

Báo cáo nền §6.3 hạng mục 4 đề nghị "chặn nến giá 0 ở đường ghi NGÀY (`backfill.py:350` và `:375`)". **Bỏ đề nghị đó.** Nó mâu thuẫn với §6.1 của chính báo cáo: ở đó tôi kết luận 71.439 dòng giá 0 trong `bars_daily` là **dữ liệu hợp lệ** — ngày không có giao dịch của mã kém thanh khoản, nguồn ghi vậy — và **không được xoá**. Chặn dòng mới và xoá dòng cũ là **cùng một phán quyết**: không thể vừa nói giữ vừa nói chặn.

Thêm nữa `write_daily` có **bốn** caller (`trading/collector/backfill.py:350`, `:375`, `scripts/backfill_history.py:53`, `scripts/backfill_universe.py:112`), nên chặn ở đường ghi còn là sửa bốn chỗ để đạt một thứ ta đã quyết là không muốn.

**Chốt:** thiệt hại nằm **toàn bộ ở đường ĐỌC**, nơi `0` được đọc thành một cái giá. Bịt ở đường đọc còn che được mọi nguồn sinh số 0 khác trong tương lai, không chỉ SSI. **Đợt này không sửa một dòng nào trong đường ghi.**

---

## §2. Phạm vi phẫu thuật

### Được sửa

| File | Task |
|---|---|
| `trading/storage/db.py` | A (hàm `compute_nav`), B (hàm `read_last_close`) |
| `scripts/seal.py` | C — **file mới**, chứa đúng một hằng số + docstring |
| `scripts/measure_crypto_strategies.py` | C (hàm `read_crypto_bars`) |
| `scripts/measure_candlestick_strategies.py` | C (SQL) |
| `scripts/measure_candlestick_patterns.py` | C (SQL) |
| `scripts/measure_octopus_combo_hybrid.py` | C (SQL) |
| `scripts/optimize_octopus_combo_hybrid.py` | C (SQL) |
| `tests/test_storage.py`, `tests/test_nav_vn_market_time.py` | test cho A |
| `tests/test_engine_main.py` | test cho B (mức hành vi GUARD-1) |
| `tests/test_crypto_seal.py` | **file mới** — test cho C |

### KHÔNG được đụng

- **Bất kỳ đường GHI nến nào**: `db.py::write_daily`, `write_bars`, `backfill.py`, `collector/main.py`, `scripts/backfill_*.py`. Lý do ở §1.2.
- `trading/storage/db.py::read_latest_bar` — xem §3.1, cố ý để nguyên.
- `scripts/measure_cross_sectional.py` — nó `import read_crypto_bars`, được che tự động; sửa thêm là dư.
- `scripts/screen_vcp_daily.py`, `scripts/screen_smc_stock_daily.py`, `trading/metrics.py` — thuộc đợt trả nợ kỹ thuật sau, **không** chen vào đây.
- Mọi hằng số đã tiền đăng ký của các phép đo. Không đổi ngưỡng, không đổi cửa sổ.
- `exclusions.txt`, `.env`, `docker-compose.yml`.

### Quy tắc truy vết

Mọi dòng code thay đổi phải truy ngược được về đúng một Task A/B/C dưới đây. Phát hiện vấn đề ngoài phạm vi thì **báo lại**, không tự sửa.

---

## §3. Phần 1 — đường tiền thật

### §3.1. Task A — `compute_nav`: giá ≤ 0 là "không định giá được"

**Hiện trạng** (`db.py:846-888`). `compute_nav` là hàm **thuần**, nhận `price_fn(symbol) -> (price, ts) | None`, và đã có khái niệm `unpriced` với hai nhánh: không có giá, và giá quá cũ. Cả hai nhánh đều "tính 0 **và** đưa vào `unpriced`". Nhưng một `price` bằng 0 trả về từ `price_fn` đi thẳng vào `nav += qty * price` mà **không** vào `unpriced` — tức tính 0 mà **không ai biết**, đúng thứ docstring của chính hàm này nói là tệ hơn:

> `khong co gia / qua cu -> TINH 0 va them vao danh sach "khong dinh gia duoc" (canh bao — NAV tinh hut ma khong ai biet thi te hon NAV khong tinh)`

**Việc phải làm.** Thêm nhánh thứ ba: `price <= 0` → `unpriced.append(symbol)` + `continue`. Cùng khuôn với hai nhánh đã có, cùng style comment.

**Vì sao đặt ở `compute_nav` chứ không ở `read_latest_bar`** (đây là điểm tôi đổi so với báo cáo nền): `compute_nav` là **chỗ thắt duy nhất** mà mọi nguồn giá đi qua — `read_latest_bar` chỉ là một `price_fn` trong số đó. Bịt ở chỗ thắt che được cả nguồn giá tương lai; bịt ở từng reader thì phải nhớ bịt lại mỗi lần thêm reader. Và `compute_nav` thuần nên test được không cần DB. **Cố ý để `read_latest_bar` nguyên** — nó chỉ báo cáo cái nó đọc được; việc phán "0 không phải giá" là việc của người dùng giá.

**Tại sao quan trọng:** NAV là mẫu số của cỡ lệnh 1% rủi ro (xem `main.py` NAV-CI). NAV hụt ⇒ cỡ lệnh hụt, im lặng.

### §3.2. Task B — `read_last_close`: bỏ qua dòng giá ≤ 0

**Hiện trạng** (`db.py:348-365`): hai truy vấn `ORDER BY ts DESC LIMIT 1`, `bars` trước rồi `bars_daily`, trả `row[0]` bất kể giá trị.

**Việc phải làm.** Thêm `AND close > 0` vào **cả hai** truy vấn, để hàm trả về giá đóng cửa **hợp lệ** gần nhất. Giữ nguyên hợp đồng hiện có: hết cả hai bảng → `None` → caller bỏ qua im lặng (docstring hiện tại đã nói rõ điều này là chủ ý, vì "không thể kết luận" thì cảnh báo sai sẽ làm nhờn cảnh báo thật).

Không đổi thứ tự hai bảng. Không đổi giá trị trả về khi có giá hợp lệ.

**Tiêu chí thật của task này là hành vi GUARD-1**, không phải hàm: sau khi sửa, một mã giá 0 trong `cfg.symbols` **không được** làm GUARD-1 im khi trần lệnh thật thực sự không mua nổi 1 lô của mã rẻ nhất *có giá hợp lệ*.

---

## §4. Phần 2 — Task C: mốc niêm phong crypto phải BẮT BUỘC

**Hiện trạng.** Mốc niêm phong crypto là **2026-09-01** (dữ liệu từ ngày này là holdout). Sáu script đọc `bars_crypto` **không có chặn trên nào**:

| Script | Hiện trạng |
|---|---|
| `measure_crypto_strategies.py` | `read_crypto_bars(...)` có `to_date` nhưng **tuỳ chọn, mặc định `None`**; caller dòng 369 không truyền |
| `measure_cross_sectional.py` | gọi `read_crypto_bars(conn, interval="1d")` — **được che tự động khi sửa hàm trên** |
| `measure_candlestick_strategies.py` | SQL trực tiếp (dòng 212, 231) |
| `measure_candlestick_patterns.py` | SQL trực tiếp (dòng 247, 260) |
| `measure_octopus_combo_hybrid.py` | SQL trực tiếp (dòng 376, 395) |
| `optimize_octopus_combo_hybrid.py` | SQL trực tiếp (dòng 164) |

Đối chiếu: nhóm forex/BingX mới (đợt 116/117/118) **đều** ghim `SEALED_MAX_DATE = 2026-08-31` và truyền vào SQL. Nhóm crypto ra đời trước khi mốc được đặt.

**Việc phải làm.**

1. Tạo `scripts/seal.py` chứa **đúng một** hằng số và docstring giải thích vì sao nó bắt buộc:
   ```python
   CRYPTO_SEALED_MAX_TS = "2026-08-31 23:59:59+00"
   ```
   Không thêm hàm tiện ích, không thêm hằng số khác, không dời hằng số của nhóm forex vào đây (đó là nợ khác, ghi nhận chứ không trả trong đợt này).

2. `read_crypto_bars`: áp `CRYPTO_SEALED_MAX_TS` **vô điều kiện**. `to_date` chỉ được **thu hẹp thêm**, không bao giờ mở rộng — tức mốc thực tế là `min(to_date, CRYPTO_SEALED_MAX_TS)`. Sau khi sửa, **không còn đường đi nào** của hàm trả về dữ liệu không chặn trên.

3. Bốn script SQL trực tiếp: thêm `AND ts <= %s` với tham số là hằng số import từ `scripts/seal.py`. Không đổi `ORDER BY`, không đổi cột, không đổi gì khác trong câu SQL.

**Ràng buộc quan trọng:** đợt này **KHÔNG chạy lại** phép đo nào của sáu script đó. Chạy lại là một quyết định tiền đăng ký riêng. Việc ở đây chỉ là bịt cổng.

---

## §5. Tiêu chí hoàn thành — từng bước kiểm chứng được

```
1. Task A → test: compute_nav với price_fn trả (0.0, ts_tuoi) phải cho symbol đó
   vào `unpriced` VÀ không cộng gì vào nav. Thêm ca biên price = -1.
   → kiểm bằng: uv run pytest tests/test_nav_vn_market_time.py tests/test_storage.py -v

2. Task B → test hàm: read_last_close bỏ qua dòng close = 0 ở CẢ hai bảng
   (hai test riêng: một cho `bars`, một cho fallback `bars_daily`).
   → test hành vi: GUARD-1 vẫn CRITICAL khi cfg.symbols có một mã giá 0 và trần
     lệnh không đủ 1 lô của mã rẻ nhất CÓ GIÁ HỢP LỆ.
   → kiểm bằng: uv run pytest tests/test_engine_main.py tests/test_storage.py -v

3. Task C → test: read_crypto_bars KHÔNG trả dòng có ts >= 2026-09-01 kể cả khi
   to_date=None; và khi truyền to_date SỚM hơn mốc thì mốc sớm hơn thắng.
   → kiểm bằng: uv run pytest tests/test_crypto_seal.py -v

4. Toàn suite → uv run pytest -m "not integration" -q  (phải ≥ 1.244 passed,
   0 failed — 1.244 là số của đợt 120, số mới phải LỚN HƠN vì có test mới)

5. Linter → uv run ruff check trading tests scripts/seal.py và các script đã sửa

6. Đếm dòng thật sau khi bịt mốc (bằng chứng cổng có tác dụng, KHÔNG phải chạy
   lại phép đo): với mỗi script đã sửa, in số dòng đọc được TRƯỚC và SAU.
   Chênh lệch phải đúng bằng số dòng vượt mốc: 1d 52 dòng, 1h 1.088 dòng.
   → nếu chênh lệch khác, DỪNG và báo — nghĩa là hiểu sai mốc hoặc sai cột.
```

---

## §6. Sáu phép phá thử bắt buộc

Mỗi phép: sửa **một** dòng cho sai, chạy test, **phải RED**, rồi phục hồi và xác nhận GREEN lại. Nộp cả bằng chứng lỗi thật (không phải mô tả).

| # | Đột biến | Test phải RED |
|---|---|---|
| 1 | Bỏ hẳn nhánh `price <= 0` trong `compute_nav` | test `unpriced` của Task A |
| 2 | Đổi `price <= 0` thành `price < 0` | ca biên `price = 0` của Task A |
| 3 | Bỏ `AND close > 0` khỏi truy vấn `bars` | test `bars` của Task B |
| 4 | Bỏ `AND close > 0` khỏi truy vấn `bars_daily` | test fallback của Task B |
| 5 | Cho `to_date` ghi đè được mốc (tức dùng `to_date or MOC` thay vì `min`) | test "to_date không mở rộng được" của Task C |
| 6 | Bỏ `AND ts <= %s` ở một trong bốn script SQL | test niêm phong của script đó |

**Cảnh báo từ kinh nghiệm phiên này** (ba lần tôi tự làm hỏng phép phá thử của chính mình):
- File trong repo là **CRLF**. Thay chuỗi bằng pattern LF sẽ **không khớp** và đột biến **không được áp** — test xanh giả.
- Sau mỗi lần sửa, **in ra `changed=True` và grep lại file** để chứng minh đột biến đã vào.
- Phục hồi bằng bản sao lưu **tạo sau** khi đã sửa xong, không phải bản trước đó — khôi phục từ bản cũ sẽ lặng lẽ xoá luôn bản sửa thật.
- PowerShell `>` ghi UTF-16; `Set-Content -Encoding utf8` chèn BOM. Dùng `[System.IO.File]::WriteAllText` với `UTF8Encoding($false)`.

---

## §7. Bằng chứng phải nộp

1. Diff đầy đủ từng Task, kèm đường dẫn + số dòng.
2. Output nguyên văn của từng lệnh ở §5, kèm exit code.
3. Bảng sáu phép phá thử với **thông điệp lỗi thật**.
4. Bảng đếm dòng trước/sau của §5 mục 6.
5. `npx gitnexus status` và `gitnexus_impact` cho `compute_nav`, `read_last_close`, `read_crypto_bars`. **Lưu ý:** MCP gitnexus `CONNECT_TIMEOUT` suốt phiên của Claude, index báo stale. Nếu agent cũng không gọi được thì **nói rõ là không gọi được**, rồi thay bằng grep caller thủ công và báo blast radius tìm được. **Không** tự chạy `npx gitnexus analyze --force`.
6. Danh sách những gì **không** kiểm được và vì sao.
7. Bất kỳ chỗ nào brief này sai hoặc mơ hồ — báo lại. Ba đợt liền brief của tôi có lỗi thiết kế (118 mẫu số, 120 rổ đối chứng, và chính báo cáo nền của đợt này ở §1.1 và §1.2); giả định brief đúng là giả định sai.

---

## §8. Điều cấm

- **Không commit, không push.** Claude làm việc đó sau khi audit.
- Không đặt/sửa/huỷ lệnh thật, không bật `real_trading_enabled`, **không chạy `--send`**.
- Không rebuild / restart container. Claude vừa rebuild engine + collector lúc 21:40 ngày 28/09; nếu đợt này đổi `trading/` thì **Claude** rebuild sau khi commit.
- **Cấm `git checkout`, `git restore`, `git stash`.** Sao lưu đặt **ngoài** repo.
- Không đọc dữ liệu từ mốc niêm phong: cổ phiếu từ 2023-01-01; VN30F từ 01/08/2026; crypto/BingX từ 2026-09-01.
- Không xoá dòng nào trong bất kỳ bảng nào. Đặc biệt **không** xoá 71.439 dòng giá 0 của `bars_daily` — xem §1.2.
- Không in giá trị biến môi trường; không đọc nội dung `.env` (chỉ được xem tên biến và độ dài).
- Không đoán phí/endpoint/bước khối lượng BingX — dẫn tài liệu chính thức hoặc phản hồi API thật.
- Không sửa dead code có từ trước, không "tiện thể" refactor.

---

## §9. Giả định của tôi — nếu sai thì dừng và hỏi

1. **Mốc niêm phong crypto là `2026-09-01`**, nên mốc đọc tối đa là `2026-08-31 23:59:59+00`. Lấy từ đợt 116/117/118 (`SEALED_MAX_TIMESTAMP_STR = "2026-08-31 23:59:59+00"`).
2. **`bars_crypto.ts` là UTC**, nên so trực tiếp với chuỗi `+00` là đúng — khác `bars_daily` (lưu 00:00 VN = 17:00 UTC hôm trước, phải dùng `bar_date()`). Agent **phải kiểm lại** giả định này trước khi viết SQL, đừng tin tôi.
3. **Dòng `bars_daily` giá 0 là ngày không có giao dịch**, không phải rác do ta sinh ra. Căn cứ: 971 mã phần lớn kém thanh khoản, trải 2016→2024, cộng 682.287 dòng giá hợp lệ nhưng `volume = 0` cùng bản chất. Nếu agent tìm được bằng chứng ngược lại, **báo ngay** — nó đổi cả §1.2.
4. `compute_nav` là chỗ thắt duy nhất của mọi nguồn giá vào NAV. Căn cứ: chỉ `account_sync.py:270` và `main.py:353` gọi nó. Nếu có đường tính NAV thứ ba không qua `compute_nav`, **báo ngay** — Task A sẽ không đủ.
