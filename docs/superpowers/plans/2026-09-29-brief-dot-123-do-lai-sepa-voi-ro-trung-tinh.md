# Brief đợt 123 — đo lại điểm SEPA với RỔ TRUNG TÍNH: mã vừa đạt 7/7 có thắng thị trường không

**Base commit:** `d56990d` (đợt 122 đã audit).
**Người thực thi:** agent. **Người audit + commit + push:** Claude.
**Nguồn gốc:** §A.2, §A.6, §A.8, §A.9 của `docs/superpowers/research/2026-09-28-dot-120-do-diem-sepa.md`.

---

## §0. Câu hỏi, và vì sao phải đo lại

Đợt 120 định hỏi *"cổ phiếu vừa đạt đủ 7/7 tiêu chí Trend Template có lợi suất vượt trội so với thị trường không?"*. Nhưng rổ đối chứng của nó (`compact_control_series` trong `screen_vcp_daily.py`) **chỉ gồm các mã đang đạt 7/7**. Nên thực chất nó trả lời một câu khác: *"mã vừa vào 7/7 có thắng các mã đã ở 7/7 không"*. Lỗi đó nằm ở brief của Claude, không phải ở agent.

Đợt này hỏi lại **đúng câu ban đầu**, bằng một rổ trung tính: **mọi mã đủ thanh khoản và vào được lệnh trong ngày đó**, không có điều kiện xu hướng nào.

Phần 1 dời máy rổ trung tính (đang nằm trong `screen_smc_stock_daily.py` của đợt 101) sang thư viện, **không đổi một con số nào**, giống cách đợt 122 đã làm. Phần 2 dùng nó để đo.

---

## §1. Phần 1 — dời máy rổ trung tính sang `trading/stock_study.py`

### §1.1. Dời đúng năm tên này, từ `scripts/screen_smc_stock_daily.py`

`BasketEntry`, `make_basket_entry`, `basket_for_day`, `baseline_for_basket`, `excess_k`.

Thân hàm dời **nguyên văn**. Claude sẽ so bằng AST như đã làm ở đợt 122: thân hàm chỉ được khác đúng ở những chỗ §1.2 cho phép.

### §1.2. Hai phụ thuộc ngầm phải lộ ra, cùng quy tắc với §2.3 đợt 122

| Hàm | Hiện đang đọc ngầm | Sau khi dời |
|---|---|---|
| `make_basket_entry` | mặc định `min_turnover=MIN_TURNOVER_VND`, `ks=TARGET_KS` của **đợt 101**; và bên trong gọi `liquidity_ok(..., window=TURNOVER_WINDOW, ...)` với `TURNOVER_WINDOW` là biến toàn cục của module đợt 101 | `min_turnover`, `window`, `ks` là **keyword bắt buộc**; truyền `window` xuống `liquidity_ok` |
| `excess_k` | `MIN_CONTROL` — **biến toàn cục** của module đợt 101, đọc bên trong thân hàm | thêm keyword bắt buộc `min_control`, thay cho việc đọc biến toàn cục |

Mọi nơi gọi truyền tường minh hằng số của **chính đợt đo đó**. `screen_smc_stock_daily.py` (dòng 399 hiện gọi `make_basket_entry(sym, bars, i, ex)` dựa hoàn toàn vào mặc định) phải truyền hằng của đợt 101.

### §1.3. Giữ nguyên

`ControlEntry`, `basket_baseline`, `excess_for_event`, `SymbolData`, `compact_control_series` **ở lại** `screen_vcp_daily.py`. Chúng là máy rổ của đợt 99, và chế độ mặc định ở Phần 2 vẫn cần chúng để tái lập đợt 120.

**Không gộp** hai bộ máy rổ. Hai bộ khác nhau thật: kiểu phần tử, `TARGET_KS`, và giá trị trả về khi rổ rỗng (xem §A.9 báo cáo đợt 120). Đợt này chỉ **dời** bộ trung tính.

### §1.4. Cổng của Phần 1

Chạy `screen_smc_stock_daily.py` trước và sau khi dời. Đầu ra phải **y hệt từng ký tự**, trừ dòng `Tổng: ...s (đọc dữ liệu ...)`. Script này chỉ có một nguồn thay đổi là Phần 1, nên chạy nó là đủ. `score_sepa_daily`, `screen_vcp_daily` và `screen_momentum_portfolio` không dùng năm tên này.

**Bắt buộc đặt `PYTHONPATH` bằng thư mục gốc repo** trước khi chạy `screen_smc_stock_daily.py`, `screen_momentum_portfolio.py` và `measure_sepa_score_edge.py`. Ba script này import `from scripts...` và **sẽ chết ngay** với `ModuleNotFoundError: No module named 'scripts'` nếu chạy trần bằng `uv run python scripts/<ten>.py`. Bản gốc cũng vậy; đây là đặc tính có sẵn, **không** phải lỗi của đợt này. Đừng "sửa" nó.

```powershell
$env:PYTHONPATH = (Get-Location).Path
```

---

## §2. Phần 2 — thêm chế độ rổ trung tính vào `measure_sepa_score_edge.py`

### §2.1. Vì sao sửa script này thay vì viết script mới

Toàn bộ máy tính điểm, dò sự kiện và RS đã nằm sẵn trong script này (`compute_score_series`, `compute_rolling_rs_raw`, `find_score_events`, …). Viết script mới thì phải chép lại, hoặc import script-sang-script, tức đúng món nợ đợt 122 vừa trả. Nên đợt này **chỉ thêm một cờ**: rổ nào được dùng.

### §2.2. Cờ mới

```
--basket {trend,neutral}     mặc định: trend
```

- `trend` là hành vi hiện tại. **Đầu ra phải y hệt đợt 120 từng ký tự** (xem §4 cổng 2).
- `neutral` là phép đo mới của đợt này. Thư mục ghi mặc định **khác**: `docs/superpowers/research/dot-123-output/`. Chế độ `neutral` **không bao giờ** được ghi vào `dot-120-output/`.

### §2.3. Chế độ `neutral` thay ĐÚNG MỘT bước: bước 5, dựng rổ đối chứng cùng ngày

Hiện tại bước 5 (quanh dòng 474–490) dựng `control_by_day` từ `store_control`, tức từ `compact_control_series(sd)`, và hàm đó bỏ qua mọi nến không thoả `trend_ok AND liq_ok`. Ở chế độ `neutral`:

1. **Dân số rổ:** mọi mã trong vũ trụ (sau `exclusions.txt`, sau `clean_bars`, sau `validate_sealed_bars`) **kể cả mã có ít hơn `TREND_MIN_BARS + 1` nến**. Lý do: rổ trung tính đại diện cho *thị trường mà nhà đầu tư mua được hôm đó*, và mã mới niêm yết vẫn mua được. Hiện vòng đọc dữ liệu bỏ hẳn các mã này (`continue` trước khi vào `sd_by_sym`). Ở chế độ `neutral` phải **giữ nến của chúng lại cho rổ**, nhưng **không** cho chúng sinh sự kiện: sự kiện vẫn cần điểm SEPA, mà điểm cần đủ 252 nến.
2. **Một mã vào rổ của ngày d** khi và chỉ khi `make_basket_entry(sym, bars, i, ex, min_turnover=MIN_TURNOVER_VND, window=TURNOVER_WINDOW, ks=TARGET_KS)` khác `None`, với `i` là nến có `bar_date(bars[i]) == d`. Tức là: đủ thanh khoản, vào được lệnh ở phiên sau (không mở trần, có khối lượng), và có ít nhất một lợi suất mục tiêu. **Không có điều kiện xu hướng nào.** Các hằng số lấy từ đợt 99 và đợt 120, như đợt 120 đã tiền đăng ký.
3. Chỉ dựng rổ cho các ngày có sự kiện (giống cả đợt 101 lẫn đợt 120), để khỏi tốn bộ nhớ.
4. **Bước 6:** `peers = basket_for_day(basket_by_day[d], e.symbol)`, rồi `excess_k(e.r.get(k), peers, k, min_control=MIN_CONTROL)`. `basket_for_day` đã loại chính mã sự kiện khỏi rổ của nó.

Mọi bước khác (tính điểm, dò sự kiện, RS, bootstrap, bảng) **giữ nguyên**. Chế độ `trend` không được đi qua bất kỳ dòng code mới nào.

### §2.4. Cổng tiền đăng ký của chế độ `neutral` — chốt TRƯỚC khi thấy số

**Kiểm định chính (đúng một, m = 1):** sự kiện *chuyển vào* điểm 7 (`mode="transition"`, score 7), khung **K = 20**, lợi suất vượt trội so với rổ trung tính cùng ngày.

**Đạt khi và chỉ khi cả bốn điều kiện đều đúng, và CẢ BỐN dùng TRUNG BÌNH:**

| # | Điều kiện |
|---|---|
| 1 | **trung bình** excess K=20 > 0 |
| 2 | số sự kiện có excess K=20 hợp lệ ≥ `MIN_EVENTS` (100) |
| 3 | cận dưới KTC 95% của `bootstrap_by_month` > 0 |
| 4 | p một phía (tỷ lệ trung bình bootstrap ≤ 0) < 0,05 sau `holm_adjust` với m = 1 |

**Vì sao đổi sang trung bình — sửa lỗi brief đợt 120:** cổng đợt 120 lấy điều kiện 1 theo **trung vị**, còn điều kiện 3 và 4 theo **trung bình** (vì `bootstrap_by_month` bootstrap trung bình). Nên có lúc trung vị −2,50% nằm **ngoài** KTC [−1,13%, +0,01%]: đọc bảng mà không biết điều này thì sẽ tưởng có lỗi tính toán. Lần này cả bốn điều kiện cùng một thống kê. Trung bình cũng là thứ một danh mục thực sự nhận được.

Viết thành một hàm **mới**, `evaluate_gate_mean`. **Không** sửa `evaluate_gate`, vì chế độ `trend` phải tái lập đợt 120 nguyên văn.

**Mô tả, KHÔNG vào cổng** (in ra, gắn nhãn "Thứ cấp"):
- Trung vị excess, và excess ở K = 5 và K = 10.
- Tám nhóm điểm 0..7 (dạng chuyển trạng thái và dạng trạng thái kéo dài). Lần này bảng tám nhóm **đọc được** như một phát biểu về sức dự báo của điểm, vì cả tám nhóm cùng trừ một rổ **thị trường**, không phải rổ 7/7.
- Tách RS ≥ 70 và RS < 70 trong nhóm 7/7.
- Chia đôi thời gian: trung bình excess K=20 của nhóm 7/7 trong 2016-01-04 → 2019-12-31 và 2020-01-01 → 2022-11-30, mỗi nửa kèm số sự kiện.
- Lợi suất **ròng** (`r_net`, đã trừ phí, thuế, trượt giá) trung bình ở K=20 của nhóm 7/7. Excess là **gộp** trừ **gộp**: nó đo khả năng chọn mã, không đo tiền thật về túi.
- Số mã trung bình trong rổ trung tính mỗi ngày có sự kiện, cộng min và max. Đây là bằng chứng rổ thật sự là "thị trường" (phải hàng trăm mã) chứ không phải vài chục.

### §2.5. Diễn giải đã chốt trước

- **Đạt:** trong mẫu 2016–2022, mã vừa đạt 7/7 có lợi suất vượt trội dương so với thị trường sau 20 phiên. Chưa phải chiến lược: chưa qua holdout 2023+ (vẫn niêm phong; mở hay không là **quyết định của chủ dự án**), và excess là gộp.
- **Không đạt:** phép đo âm thứ 13 của dự án. Bảng điểm SEPA của đợt 119 vẫn dùng được để **mô tả** trạng thái kỹ thuật, nhưng không có bằng chứng là nó **chọn** được mã thắng thị trường.
- **Không có vùng xám.** Không được viết "gần đạt", "có xu hướng", "đáng chú ý" về một kết quả không đạt.

### §2.6. Chạy đúng MỘT lần

Chạy `--basket neutral` đầy đủ **một lần**, sau khi mọi test đã xanh. Nếu phải sửa code rồi chạy lại vì một lỗi thật, ghi **mọi** lần chạy: giờ chạy, lý do chạy lại, và diff của bản sửa. **Cấm** đổi bất kỳ hằng số, định nghĩa rổ, hay điều kiện cổng nào sau khi đã thấy số.

---

## §3. Phạm vi phẫu thuật

**Được sửa:** `trading/stock_study.py`, `scripts/screen_smc_stock_daily.py` (chỉ Phần 1), `scripts/measure_sepa_score_edge.py`, `tests/test_screen_smc_stock_daily.py`, `tests/test_measure_sepa_score_edge.py`, và `tests/test_stock_study.py` nếu cần.

**Được tạo:** `docs/superpowers/research/2026-09-29-dot-123-do-lai-sepa-voi-ro-trung-tinh.md` (báo cáo) và `docs/superpowers/research/dot-123-output/`.

**KHÔNG được đụng:** `screen_vcp_daily.py`, `score_sepa_daily.py`, `screen_momentum_portfolio.py`; mọi file trong `trading/` ngoài `stock_study.py`; `exclusions.txt`; **mọi file trong `dot-*-output/` cũ**; mọi hằng số tiền đăng ký.

Mọi dòng thay đổi phải truy ngược được về §1 hoặc §2. Được sửa định dạng **chỉ** khi ruff đòi.

---

## §4. Tiêu chí hoàn thành

```
Cổng 1 (Phần 1). screen_smc_stock_daily.py trước/sau: y hệt từng ký tự, trừ dòng thời gian.
         → kiểm bằng: lệnh so + output nguyên văn.

Cổng 2 (chế độ trend không đổi). measure_sepa_score_edge.py --output-dir <ngoai_repo>
         (mặc định --basket trend) cho summary_table_with_exclusions.txt TRÙNG HASH với
         docs/superpowers/research/dot-120-output/summary_table_with_exclusions.txt,
         và full_run_output_with_exclusions.txt chỉ khác hai dòng "Chạy lúc:" và "Thời gian:".
         → kiểm bằng: Get-FileHash và diff nguyên văn.

Cổng 3. Test đơn vị mới (dữ liệu tổng hợp, không cần DB):
         a. rổ trung tính CHỨA một mã KHÔNG đạt trend_ok nhưng đủ thanh khoản và vào được lệnh;
         b. rổ trung tính KHÔNG chứa mã dưới ngưỡng thanh khoản;
         c. rổ trung tính KHÔNG chứa mã mở trần ở phiên sau;
         d. rổ của một sự kiện KHÔNG chứa chính mã sự kiện;
         e. rổ trung tính CHỨA một mã có ít hơn 253 nến nhưng đủ điều kiện a;
         f. evaluate_gate_mean: với dữ liệu có trung bình > 0 nhưng trung vị < 0, điều kiện 1 ĐÚNG.

Cổng 4. uv run pytest -q   (TOÀN BỘ suite, KHÔNG lọc marker; mốc 1.396 passed, phải ≥ 1.396, 0 failed)
Cổng 5. uv run ruff check trading tests scripts/screen_smc_stock_daily.py scripts/measure_sepa_score_edge.py
         → sạch. (Đợt 122 chỉ lint `trading tests` nên bỏ lọt 7 lỗi import trong script; lần này lint cả script đã sửa.)
Cổng 6. Chạy --basket neutral một lần; nộp dot-123-output/ và báo cáo.
```

### §4.1. Bốn phép phá thử bắt buộc

Mỗi phép: sửa **một** chỗ, chạy test liên quan, **phải RED**, phục hồi, xác nhận GREEN. Nộp thông điệp lỗi thật.

| # | Đột biến | Phải bắt được bởi |
|---|---|---|
| 1 | Trong chế độ `neutral`, chỉ cho vào rổ các mã có `sd.trend_ok(i)` đúng | test 3a |
| 2 | `basket_for_day` giữ lại chính mã sự kiện | test 3d |
| 3 | `evaluate_gate_mean` điều kiện 1 dùng trung vị | test 3f |
| 4 | Vòng đọc dữ liệu vẫn `continue` với mã < 253 nến ở chế độ `neutral` (tức rổ mất mã mới niêm yết) | test 3e |

Kinh nghiệm cũ, vẫn đúng: file có thể là CRLF, nên đột biến viết bằng pattern LF sẽ không được áp và cổng sẽ xanh giả. In `changed=True` và grep lại sau mỗi lần sửa. Phục hồi bằng bản sao lưu tạo **sau** khi code đã xong.

---

## §5. Báo cáo phải có

1. **Kết luận ba dòng**, đúng một trong hai nhãn **ĐẠT** / **KHÔNG ĐẠT**, kèm bốn điều kiện và giá trị của từng điều kiện.
2. Bảng chính: tám nhóm điểm (chuyển trạng thái), với N, trung bình excess K=20, trung vị K=20, KTC, K=5, K=10.
3. Tất cả các mục "Thứ cấp" của §2.4.
4. **Bảng đặt cạnh đợt 120**: cùng nhóm 7/7 K=20, hai cột "rổ 7/7 (đợt 120)" và "rổ trung tính (đợt 123)". Đây là thứ cho thấy việc đổi mốc làm đổi câu trả lời đến đâu.
5. Output nguyên văn của sáu cổng và bốn phép phá thử.
6. `gitnexus impact` cho năm tên ở §1.1 và `gitnexus detect-changes`, qua CLI với `--repo AI_auto_trading_system`. Rủi ro HIGH/CRITICAL là dự kiến; việc của bạn là **báo** nó.
7. Những gì bạn **không** kiểm được, và vì sao.
8. Chỗ nào brief này sai hoặc mơ hồ. Brief của Claude đã sai ở đợt 118, 120 và 122; giả định brief đúng là giả định sai.

---

## §6. Điều cấm

- **Không commit, không push.** Không rebuild, không restart container.
- Không đặt, sửa, huỷ lệnh thật; không bật `real_trading_enabled`; **không chạy `--send`**.
- **Cấm `git checkout`, `git restore`, `git stash`.** Sao lưu đặt ngoài repo.
- **Không đọc dữ liệu cổ phiếu từ 2023-01-01 để đo.** `READ_TO` và `validate_sealed_bars` giữ nguyên.
- **Không ghi đè** bất kỳ file nào trong `docs/superpowers/research/dot-*-output/` đã có.
- Không đổi hằng số tiền đăng ký, định nghĩa rổ, hay điều kiện cổng sau khi đã thấy số.
- Không in giá trị biến môi trường; không đọc nội dung `.env`.
- Không "tiện thể" refactor, không sửa dead code có từ trước.

---

## §7. Giả định của tôi — sai thì dừng và báo

1. `make_basket_entry` **không** có điều kiện xu hướng nào. Căn cứ: thân hàm chỉ gọi `liquidity_ok`, `entry_status`, `compute_targets`. Nếu thấy khác, **dừng**: đó chính là lỗi đợt 120 lặp lại.
2. Đợt 120 dựng rổ chỉ cho ngày có sự kiện, và việc thêm mã < 253 nến vào rổ **không** làm đổi đầu ra của chế độ `trend`. Cổng 2 kiểm điều này.
3. `bootstrap_by_month` bootstrap **trung bình**, nên KTC và p của nó khớp với điều kiện 1 theo trung bình. Căn cứ: thân hàm tính `sum(vals) / len(vals)` cho mỗi mẫu bootstrap.
4. Rổ trung tính mỗi ngày có sự kiện sẽ có **hàng trăm** mã. Nếu số trung bình dưới 50, **dừng và báo** trước khi viết kết luận: nghĩa là rổ không đại diện cho thị trường.
