# Brief đợt 101 — Sàng lọc SMC trên cổ phiếu VN, nến ngày, nhiều mã, giữ 2–8 tuần, đăng ký trước

Ngày giao: 26/09/2026 (thứ Bảy). Base: main `ae0953c`.
Người giao, audit, commit, push: Claude. Người thực thi: **Gemini Flash 3.8**. Agent **KHÔNG** commit, **KHÔNG** push.
Làm được ngay cuối tuần. Chỉ **đọc** DB. **Không** đụng container, máy ghi sổ lệnh, Task Scheduler, `trading/`, và mọi file có sẵn.

---

## 0. Vì sao có đợt này

Đợt 98 chỉ đo SMC trên **phái sinh VN30F, trong phiên, giữ 5–30 phút**. Chủ dự án chỉ ra đúng rằng cách dùng thật của họ là **nhiều mã cổ phiếu, giữ trên một tuần**, và cách đó **chưa được đo**. Kết luận "SMC không có lợi thế" hiện chỉ đúng cho phái sinh trong phiên.

Đợt này đo SMC theo cách của chủ dự án, **trong đúng khung của đợt 99 (VCP)**: cùng vũ trụ mã, cùng lọc thanh khoản, cùng giai đoạn, cùng niêm phong, cùng cách vào/thoát lệnh và chi phí, cùng bootstrap theo khối tháng. Nhờ vậy hai kết quả **so được với nhau**.

**Chỉ chiều mua**: cổ phiếu VN không bán khống được.

Kết quả âm là kết quả hợp lệ.

---

## 1. Thiết kế ĐĂNG KÝ TRƯỚC — mọi tham số chốt ở đây, KHÔNG được đổi

**Chạy phép đo thật ĐÚNG MỘT LẦN.** Có lỗi code phải chạy lại thì dán **tất cả** các lần kèm lý do. Không thử biến thể, không chỉnh ngưỡng, không thêm sự kiện.

### 1.1 Dữ liệu — y hệt đợt 99, trừ một mốc

- Vũ trụ, loại mã hỏng (`exclusions.txt`), bỏ nến rác, thanh khoản ≥ 1 tỷ đồng (trung bình 20 nến **trước** `t`), múi giờ VN, giữ các mã đã ngừng giao dịch: **y hệt đợt 99 §1.1**.
- **Niêm phong từ 2023-01-01**: code phải ném lỗi, như đợt 99.
- **Khác đợt 99:** nến tín hiệu `t` trong **2016-01-04 → 2022-10-31**, vì khung giữ dài nhất là 40 phiên. Dữ liệu đọc tới 2022-12-31. **Mọi** khung dùng **cùng** mốc này để các khung so được với nhau.

### 1.2 Ba sự kiện SMC trên nến ngày, chỉ chiều mua

Tính tại **đóng cửa nến `t`**, chỉ dùng nến ≤ `t` của **cùng mã**. Mỗi sự kiện được đo **như một chiến lược riêng**.

**(a) `sweep` — quét đáy rồi quay lên.** `N = 20` phiên, cần `t ≥ 20`:
`L = min(low[t−20 … t−1])`. Sự kiện khi `low[t] < L` **và** `close[t] > L`.

**(b) `bos` — phá đỉnh dao động.** Swing high theo **fractal k = 2**: nến `j` là swing high nếu `high[j]` **lớn hơn hẳn** high của `j−2, j−1, j+1, j+2`.
- **Swing tại `j` chỉ được BIẾT từ nến `j+2`.** **Dùng lại** `_la_swing_high` của `scripts/screen_vn30f_smc.py`, không viết lại định nghĩa fractal.
- `S_h` = swing high đã xác nhận **gần nhất** với `j + 2 ≤ t`. Sự kiện khi `close[t−1] ≤ S_h` **và** `close[t] > S_h`.

**(c) `fvg` — khoảng trống giá tăng.** Cần `t ≥ 2`: sự kiện khi `low[t] > high[t−2]`.

**Chung cho cả ba:**
- `volume[t] > 0`, và đạt thanh khoản (§1.1) tại `t`.
- **Thời gian nghỉ 20 nến** cho **từng loại sự kiện, từng mã** (tránh đếm trùng một nhịp).
- **Không** có bộ lọc xu hướng. SMC không yêu cầu nó; thêm vào là thêm một bậc tự do.

### 1.3 Vào, thoát, chi phí — dùng lại đợt 99

- Vào: `open[t+1]`. Bỏ nếu mở trần theo sàn, hoặc `volume[t+1] = 0`. **Dùng lại** `entry_status` của `scripts/screen_vcp_daily.py`.
- Thoát: `close[t+k]` với **`k ∈ {10, 20, 40}`** (khoảng 2, 4 và 8 tuần). **Dùng lại** `compute_targets(bars, t, ks=(10, 20, 40))`.
- Lợi nhuận ròng: **dùng lại** `net_return` (phí, thuế, trượt giá import từ `paper_broker`).
- Không đủ `k` nến sau `t` thì bỏ sự kiện cho khung đó, **đếm và báo**.

### 1.4 Đối chứng cùng ngày

- **Rổ đối chứng** của ngày `t` = mọi mã khác trong vũ trụ đạt **thanh khoản** tại `t`, và vào/thoát được theo đúng quy ước §1.3.
  - **Không** có điều kiện xu hướng, vì sự kiện SMC cũng không có.
  - Điểm này **khác đợt 99**: rổ của VCP là các mã đạt trend template. Ghi rõ khác biệt trong báo cáo.
- `baseline_k(t)` = trung bình `r_k` gộp của rổ; `excess_k = r_k(sự kiện) − baseline_k(t)`. Rổ dưới 5 mã thì loại khỏi phép so vượt trội, **đếm và báo**.
- `ControlEntry` của đợt 99 **chỉ có các khung 5/10/20**, nên **không** dùng được cho khung 40. Viết cấu trúc rổ đối chứng mới trong file của đợt này, lưu `{k: r_k}` cho `k ∈ {10, 20, 40}`. **Không** sửa `screen_vcp_daily.py`.

### 1.5 Kiểm định — ba phép thử chính, hiệu chỉnh Holm

- **Chính:** với mỗi sự kiện `sweep`, `bos`, `fvg`, ở **`k = 20`**: giả thuyết trung bình `excess_20 > 0`, một phía. **Dùng lại** `bootstrap_by_month` (khối tháng, 2.000 lần, `seed = 42`).
- **Ba phép thử nên phải hiệu chỉnh Holm:** sắp ba giá trị p tăng dần `p(1) ≤ p(2) ≤ p(3)`, so lần lượt với `0,05/3`, `0,05/2`, `0,05/1`. Dừng ở giá trị đầu tiên không đạt; các giá trị sau cũng không đạt. In cả p gốc lẫn kết quả Holm.
- **Kết luận "CÓ LỢI THẾ" cho một sự kiện khi cả ba điều kiện đúng:**
  (a) đạt Holm ở `k = 20`;
  (b) trung bình `r_20_net > 0`;
  (c) **trung vị** `excess_20 > 0`.
- `k = 10` và `k = 40`: **chỉ mô tả**, KHÔNG kết luận.
- Sự kiện nào có dưới 100 lần hợp lệ thì ghi `IT_SU_KIEN` và không kết luận.

---

## 2. Phạm vi

- **Được thêm:** `scripts/screen_smc_stock_daily.py`, `tests/test_screen_smc_stock_daily.py`.
- **Chỉ import, không sửa:**
  - từ `scripts/screen_vcp_daily.py`: `load_universe`, `clean_bars`, `validate_sealed_bars`, `liquidity_ok`, `entry_status`, `compute_targets`, `net_return`, `bootstrap_by_month`, `bar_date`, `month_key`, `apply_cooldown`;
  - từ `scripts/screen_vn30f_smc.py`: `_la_swing_high`;
  - `resolve_dsn` từ `scripts/_db_common.py`, `Storage`, `TZ`.
- **Cấm** chép lại bất kỳ hàm nào ở trên. Nếu một hàm không dùng lại được như nó đang là, **dừng và báo**, không tự sửa file gốc.
- Không pandas/numpy (repo không có).
- Trước khi viết: `gitnexus_context` cho `compute_targets` và `bootstrap_by_month`. Sau khi viết: `gitnexus_detect_changes()`.

---

## 3. Kiểm chứng (TDD: viết test trước, thấy đỏ, rồi mới viết code)

Test trên chuỗi nến dựng tay. Nến dựng tay có giá khoảng 100 đồng, nên **truyền ngưỡng thanh khoản nhỏ** vào test hình dạng, giống cách đợt 99 dùng `min_turnover` sau audit.
- **Bắt buộc** có **một** test ghim rằng lần chạy thật dùng ngưỡng **1 tỷ**.
- **Bắt buộc** có **một** test chứng minh sự kiện dưới ngưỡng thanh khoản **không** được tính. Đây là lỗi Claude bắt ở đợt 99.

1. `sweep`: `low[t]` thủng đáy 20 phiên và đóng cửa trên đáy → sự kiện. Đóng cửa **bằng** đáy → không. `low[t]` **bằng** đáy → không.
2. `bos`: swing high ở `j`. Tại `t = j+1`, swing chưa được biết → **không** được dùng. Tại `t ≥ j+2`, đóng cửa vượt → sự kiện. `close[t−1]` đã ở trên swing → không (không phải phá mới).
3. `fvg`: `low[t] = high[t−2]` → **không** (phải lớn hơn hẳn); lớn hơn → có.
4. **Thời gian nghỉ** tính riêng từng loại: một mã có `sweep` ở `t` và `fvg` ở `t+5` → **cả hai** được tính; hai `fvg` cách 10 nến → chỉ 1.
5. **Chống nhìn trộm tương lai — quan trọng nhất:** sửa tùy ý mọi nến sau `t`. Cả ba sự kiện tại mọi nến ≤ `t` phải **giữ nguyên**. Chạy cho nhiều `t`.
6. **Khung 40:** sự kiện có 30 nến sau `t` → có `r_10`, `r_20`, **không** có `r_40`, và được đếm vào "thiếu dữ liệu".
7. **Rổ đối chứng:** 3 mã đạt thanh khoản cùng ngày (1 là sự kiện) và 1 mã không đạt → rổ chỉ gồm 2 mã đạt, không có mã sự kiện. Rổ dưới 5 mã → loại khỏi phép so vượt trội.
8. **Holm:** p = (0,010; 0,020; 0,040) → cả ba đạt. p = (0,020; 0,020; 0,040) → cả ba **không** đạt (0,020 > 0,0167). p = (0,001; 0,030; 0,040) → chỉ cái đầu đạt (0,030 > 0,025, và dừng ở đó). Tính tay trong docstring.
9. **Mốc IS:** nến tín hiệu ngày 2022-11-01 giờ VN → **ngoài** IS. Nến có `ts = 2022-10-31 17:00 UTC` là ngày 01/11 giờ VN → cũng **ngoài**.

### Kiểm thử phá hoại (bắt buộc)
Sao lưu **ra ngoài repo**. **Cấm** `git checkout`, `git restore`, `git stash`.
- Cho `bos` dùng swing chưa xác nhận → test 5 **phải đỏ**.
- Cho `sweep` tính đáy gồm cả nến `t` → test 1 đỏ.
- Bỏ lọc thanh khoản ở phía sự kiện → test thanh khoản đỏ.
- Dùng chung một thời gian nghỉ cho cả ba loại → test 4 đỏ.
- Cho Holm so mọi p với 0,05 → test 8 đỏ.
- Khôi phục, chạy lại, sạch. Báo tên test đỏ từng bước.

### Tổng
```
uv run pytest -m "not integration" -q     # mốc: 972 passed
uv run ruff check trading tests scripts
```

---

## 4. Chạy thật và đọc kết quả

`uv run python scripts/screen_smc_stock_daily.py`, **một lần**. In:
1. Vũ trụ (trước và sau khi loại), số nến rác bị bỏ.
2. Với từng sự kiện: số lần trong IS theo năm và theo sàn; số bị bỏ vì trần, volume 0, thiếu dữ liệu, rổ nhỏ.
3. Với từng sự kiện × `k ∈ {10, 20, 40}`: n; trung bình và trung vị của `r_k` gộp, `r_k_net`, `baseline_k`, `excess_k`; tỷ lệ `excess_k > 0`.
4. Ba phép thử chính (`k = 20`): trung bình `excess_20`, KTC 95%, p gốc, kết quả Holm, và kết luận theo §1.5 cho **từng** sự kiện.
5. Tỷ trọng của 10 sự kiện `excess_20` lớn nhất trong tổng (kiểm độ lệch).
6. Thời gian chạy.

**Quy tắc đọc, không tự diễn giải thêm:**
- Không sự kiện nào đạt → ghi **"SMC dạng máy trên cổ phiếu, giữ 2–8 tuần: KHÔNG có lợi thế so với cổ phiếu đủ thanh khoản cùng ngày, sau chi phí."**
- Có sự kiện đạt → **KHÔNG mở tập từ 2023**, **KHÔNG xây chiến lược**. Chỉ báo cáo. Claude quyết có mở tập niêm phong hay không, và mở một lần cho đúng sự kiện đó.

---

## 5. Báo cáo cho Claude

1. GitNexus context và detect_changes.
2. Test; kiểm thử phá hoại (tên test đỏ từng bước).
3. Pytest và ruff.
4. **Nguyên văn** toàn bộ output của lần chạy thật (tất cả các lần, nếu có chạy lại).
5. Mọi quyết định nhỏ agent phải tự chọn vì brief chưa nói: liệt kê rõ từng cái.
6. Mọi điều ngoài phạm vi: **báo cáo, không sửa.**

---

## 6. Ghi chú của planner

- **VCP không được đo lại với khung giữ dài hơn trong đợt này.** Thử thêm khung sau khi đã thấy khung 20 phiên thua là đi tìm con số đẹp. Nếu chủ dự án vẫn muốn, đó sẽ là một phép thử **riêng**, đăng ký trước, ghi rõ "thêm sau khi đã biết kết quả k=20".
- Kết luận của đợt 98 (SMC trên phái sinh trong phiên) **không bị thay** bởi đợt này. Hai đợt đo hai câu hỏi khác nhau.


---

## 7. Kết quả và audit của Claude (26/09)

**Chạy đúng một lần** (177,5 giây). Claude đã đối chiếu log gốc `run_dot101.log` với báo cáo: khớp.

| Sự kiện | n | TB r_20 ròng | TB đối chứng | TB vượt trội 20 phiên | KTC 95% | p | Trung vị vượt trội |
|---|---|---|---|---|---|---|---|
| `sweep` | 6.993 | **−2,29%** | −0,59% | **−1,01%** | [−1,52%; −0,54%] | 1,000 | −1,71% |
| `bos` | 9.725 | +0,58% | +1,46% | −0,18% | [−0,51%; +0,15%] | 0,84 | −1,85% |
| `fvg` | 14.017 | +0,35% | +1,26% | −0,21% | [−0,40%; −0,02%] | 0,98 | −1,70% |

**Kết luận: SMC dạng máy trên cổ phiếu, giữ 2–8 tuần, KHÔNG có lợi thế so với cổ phiếu đủ thanh khoản cùng ngày, sau chi phí.** Đây là phép đo âm thứ tám.
- Với `sweep` và `fvg`, **KTC nằm hoàn toàn dưới 0**: mua theo hai tín hiệu này **tệ hơn có ý nghĩa thống kê** so với mua bừa cùng ngày.
- `bos` và `fvg` có lãi ròng tuyệt đối dương, nhưng thấp hơn rổ đối chứng.
- Ở cả 9 ô (3 sự kiện × 3 khung), trung vị vượt trội đều âm, và tỷ lệ thắng rổ đối chứng chỉ 41–43%.

**Claude kiểm độc lập** vì sao trung vị `r` của `bos` đúng bằng 0,0000 (dễ là dấu hiệu lỗi chỉ số). Chỉ **123/9.725 (1,3%)** sự kiện có `r_20` đúng bằng 0. Các ví dụ là dữ liệu thật (ACB, ABI, ASM…, thanh khoản hàng chục tới hàng trăm tỷ). Phân phối gần đối xứng quanh 0, nên trung vị rơi vào dải nhỏ các giá trị bằng 0 do bước giá rời rạc. **Không phải lỗi.** Lời giải thích của agent ("47,69% nến có close = open") không liên quan: đó là giá mở và giá đóng của cùng một phiên, còn `r_20` so hai phiên khác nhau.

Code audit: swing chỉ được xác nhận tại `t = j + 2`; lọc thanh khoản áp ở phía sự kiện; thời gian nghỉ tính riêng từng loại; chỉ import các hàm của đợt 98/99, không chép. 37 test, 1009 suite, ruff sạch.

**Ghi chú sau (26/09, khi viết brief 102):** đợt 101 **không** lọc ETF/quỹ (24 mã). Claude đo số sự kiện từ các mã này: `sweep` 62/6.993, `bos` 94/9.726, `fvg` 132/14.018, **khoảng 1%** ở mỗi loại; rổ đối chứng cũng có chúng ở tỷ lệ tương tự. Không đủ để đảo kết luận (ví dụ `sweep` −1,01%, KTC nằm hẳn dưới 0). Từ đợt 102, quy tắc "đúng 3 ký tự chữ/số" loại chúng.