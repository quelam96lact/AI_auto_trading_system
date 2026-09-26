# Brief đợt 99 — Sàng lọc VCP (Volatility Contraction Pattern) trên cổ phiếu VN, nến ngày, đăng ký trước

Ngày giao: 26/09/2026 (thứ Bảy). Base: main `d8b90b0`.
Người giao, audit, commit, push: Claude. Người thực thi: **Gemini Flash 3.8**. Agent **KHÔNG** commit, **KHÔNG** push.
Làm được ngay cuối tuần. Chỉ **đọc** DB. **Không** đụng container, máy ghi sổ lệnh, Task Scheduler, `trading/`.
Không đụng Task 4 của đợt 97 (chiều thứ Hai); hai việc độc lập.

---

## 0. Vì sao VCP, và vì sao đo như thế này

VCP (Mark Minervini) là mô hình **mua một chiều, giữ vài ngày tới vài tuần, trên nến ngày**:
- cổ phiếu đang trong xu hướng tăng giai đoạn 2;
- giá tạo một nền với các nhịp điều chỉnh **hẹp dần** và khối lượng **cạn dần**;
- mua khi giá phá lên khỏi điểm pivot với khối lượng lớn.

**Khác với octopus và SMC, VCP hợp với ràng buộc của cổ phiếu VN:**
- Giữ nhiều ngày nên T+2,5 không phải vấn đề.
- Chỉ mua, nên không cần bán khống.
- Mục tiêu tính theo nhiều phần trăm, nên phí khứ hồi 0,60% chỉ là một phần nhỏ.

Dữ liệu cũng đủ: `bars_daily` có 1.554 mã, từ 2016 tới nay.

**Hai bài học bắt buộc** (từ `sma_cross` và sáu phép đo âm trước):
1. **Phải có đối chứng.** Cổ phiếu VN tăng mạnh giai đoạn 2016–2026, nên "có lãi" chỉ đo **thị trường**, không đo chiến lược. Câu hỏi đúng là: VCP có hơn việc **mua một cổ phiếu bất kỳ cũng đang trong xu hướng tăng, cùng ngày** không?
2. **Ngưỡng kinh tế phải đủ chi phí:** phí, thuế **và** trượt giá (bài học của đợt 98, khi chi phí thiếu spread).

**Kỳ vọng của Claude:** không rõ. Đây là lần đầu đo một mô hình **giữ nhiều ngày trên cổ phiếu có đối chứng cùng ngày**. Kết quả âm là kết quả hợp lệ.

---

## 1. Thiết kế ĐĂNG KÝ TRƯỚC — mọi tham số chốt ở đây, KHÔNG được đổi

**Chạy phép đo thật ĐÚNG MỘT LẦN.** Có lỗi code phải chạy lại thì dán **tất cả** các lần kèm lý do. Không thử biến thể, không chỉnh ngưỡng.

### 1.1 Dữ liệu và vũ trụ mã

- Nguồn: `bars_daily`, đọc qua `Storage.read_daily_bars(symbol, start, end)`. Ngày của nến tính theo **giờ VN**: `bars_daily` lưu 00:00 VN, tức 17:00 UTC **hôm trước**. Mọi lọc theo ngày phải qua `.astimezone(TZ).date()` hoặc `AT TIME ZONE 'Asia/Ho_Chi_Minh'`. **Cấm** `ts::date` và `.date()` trên datetime UTC.
- **Loại mã hỏng:** đọc `exclusions.txt` ở gốc repo (246 mã: chia tách chưa điều chỉnh, và mã có ≥5% nến OHLC ≤ 0), theo đúng cách `scripts/measure_market_regime.py` đọc cờ `--exclude-file`.
- **Loại nến rác:** bỏ nến có `open`, `high`, `low` hoặc `close ≤ 0`. Nến `volume = 0` **giữ nguyên trong chuỗi** (ngày không giao dịch), nhưng **không** được làm nến tín hiệu, nến vào lệnh, hay nến thoát lệnh (xem §1.5).
- **Thanh khoản, tại từng thời điểm:** trung bình `close × volume` của 20 nến **trước** nến tín hiệu phải **≥ 1 tỷ đồng**. Giá đã được điều chỉnh ngược nên con số tuyệt đối lệch ở các năm cũ; ghi hạn chế này trong báo cáo, **không** tự đổi định nghĩa.
- **Mã đã hủy niêm yết:** 185 mã trong bảng đã ngừng có nến; chúng **ở lại** trong vũ trụ. Không thể chắc bảng có đủ **mọi** mã đã hủy. Báo cáo phải ghi rằng **thiên lệch sống sót có thể còn**, và nó làm kết quả **đẹp hơn thật**.

### 1.2 Chia tập — niêm phong

- **IS:** nến tín hiệu `t` trong **2016-01-04 → 2022-11-30**. Dữ liệu được đọc tới **2022-12-31** để tính mục tiêu 20 phiên cho các sự kiện cuối IS.
- **Tập kiểm chứng: từ 2023-01-01 trở đi, NIÊM PHONG, KHÔNG đọc.** Code phải **ném lỗi** nếu đọc nến ≥ 2023-01-01, theo đúng khuôn `validate_sealed_bars` của `scripts/screen_vn30f_intraday.py`.

### 1.3 Bộ lọc xu hướng (Minervini "trend template", **không có RS rating**)

Tính tại **đóng cửa nến `t−1`** (hôm trước ngày phá vỡ). Cần ít nhất **252 nến** lịch sử. Tất cả **7** điều kiện phải đúng:
1. `close > SMA150` và `close > SMA200`
2. `SMA150 > SMA200`
3. `SMA200[t−1] > SMA200[t−21]` (SMA200 đi lên trong một tháng)
4. `SMA50 > SMA150` và `SMA50 > SMA200`
5. `close > SMA50`
6. `close ≥ 1,30 × min(low của 252 nến gần nhất)`
7. `close ≥ 0,75 × max(high của 252 nến gần nhất)`

Bỏ RS rating: nó cần xếp hạng toàn thị trường, là một thiết kế riêng. Ghi rõ điều này trong báo cáo.

### 1.4 Nền VCP và nến phá vỡ

Nền là **60 nến `t−60 … t−1`**, chia làm 3 đoạn 20 nến: `S1 = t−60…t−41`, `S2 = t−40…t−21`, `S3 = t−20…t−1`.
- Độ sâu mỗi đoạn: `depth_i = (max high_i − min low_i) / max high_i`.
- **Co hẹp:** `depth1 > depth2 > depth3`, `depth1 ≤ 0,35`, `depth3 ≤ 0,10`.
- **Khối lượng cạn:** trung bình volume của `S3` < trung bình volume của `S1`.
- **Pivot** `P = max high của S3`.
- **Nến phá vỡ `t`:** `close[t] > P` **và** `volume[t] ≥ 1,5 × trung bình volume của t−50 … t−1`.
- **Thời gian nghỉ:** sau một sự kiện ở mã X, không tính sự kiện mới cho X trong **20 nến** tiếp theo (tránh đếm trùng một nền).

**Mẹo hiệu năng (không đổi kết quả):** kiểm `close[t] > max high(t−20…t−1)` trước tiên. Điều kiện này chính là `close > P` và loại ~95% số nến. Chỉ khi nó đúng mới tính bộ lọc xu hướng và nền.

### 1.5 Vào lệnh, thoát lệnh, mục tiêu

- **Vào:** giá mở cửa của nến `t+1`.
  - **Bỏ sự kiện nếu `t+1` mở cửa ở giá trần:** `open[t+1] ≥ close[t] × (1 + biên_độ − 0,001)`, với biên độ theo `symbol_universe.exchange`: HOSE 0,07; HNX 0,10; UPCOM 0,15; sàn không rõ thì 0,07. **Đếm và báo** số sự kiện bị bỏ vì trần.
  - Claude đã kiểm (26/09): `symbol_universe.exchange` chỉ có đúng ba giá trị `HOSE` (431), `HNX` (302), `UPCOM` (862), và **mọi** mã có nến trong `bars_daily` đều có dòng trong bảng này. **Hạn chế:** đây là sàn **hiện tại**. Mã từng chuyển sàn bị áp biên độ của sàn mới cho cả giai đoạn trước. Ghi hạn chế này trong báo cáo, **không** tự dựng lịch sử chuyển sàn.
  - Bỏ nếu `volume[t+1] = 0`.
- **Mục tiêu:** với `k ∈ {5, 10, 20}`, thoát tại **giá đóng cửa của nến `t+k`**.
  - Lợi nhuận gộp: `r_k = close[t+k] / open[t+1] − 1`.
  - Lợi nhuận ròng: `r_k_net = (close[t+k] × (1 − FEE_RATE − SELL_TAX_RATE − s)) / (open[t+1] × (1 + FEE_RATE + s)) − 1`, với `s = SLIPPAGE_BPS / 10_000`. **Import** `FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS` từ `trading/paper_broker.py`. **Không** gõ 0,0025 hay 0,6%.
- Không đủ `k` nến sau `t` (hủy niêm yết, tạm ngừng, hết IS) thì bỏ sự kiện cho khung `k` đó, **đếm và báo**.

### 1.6 Đối chứng cùng ngày — lõi của phép đo

Với mỗi sự kiện ở ngày `t`: **rổ đối chứng** = mọi mã khác trong vũ trụ đạt **thanh khoản** (§1.1) **và** **bộ lọc xu hướng** (§1.3) tại `t−1`, **không** tính chính mã sự kiện, và có đủ dữ liệu vào/thoát theo đúng quy ước §1.5 (kể cả quy tắc bỏ nếu mở trần).
- `baseline_k(t)` = trung bình `r_k` **gộp** của rổ đó.
- `excess_k = r_k(sự kiện) − baseline_k(t)`.
- Rổ đối chứng có **dưới 5 mã** thì bỏ sự kiện khỏi phép so vượt trội, **đếm và báo**.

Ý nghĩa: `excess` đo phần **VCP thêm vào** so với việc mua bừa một cổ phiếu đang tăng cùng ngày. Nó loại được cả xu hướng thị trường lẫn tác động của bộ lọc xu hướng.

### 1.7 Kiểm định — MỘT phép thử chính

- **Chính (đăng ký trước):** `k = 20`. Giả thuyết là trung bình `excess_20 > 0`, kiểm **một phía**.
  - Khoảng tin cậy dùng **bootstrap theo khối tháng dương lịch**: gom sự kiện theo tháng của `t`, lấy mẫu lại **các tháng** có hoàn lại, 2.000 lần, `seed = 42`.
  - `p` = tỷ lệ mẫu bootstrap có trung bình ≤ 0.
  - **Lý do chọn khối tháng:** sự kiện VCP dồn cục theo giai đoạn thị trường, nên coi từng sự kiện là độc lập sẽ làm p nhỏ giả.
- **Phụ (chỉ mô tả, KHÔNG kết luận):** `k = 5` và `k = 10`, cùng bảng số.
- **Kết luận "CÓ LỢI THẾ" khi cả ba:**
  (a) `p < 0,05` cho `excess_20`;
  (b) trung bình `r_20_net > 0`;
  (c) **trung vị** `excess_20 > 0`. Điều kiện này để tránh kết luận dựa vào vài cú tăng cực lớn.
- IS có **dưới 100** sự kiện hợp lệ thì ghi `IT_SU_KIEN — sức mạnh thấp` và **không kết luận**.

---

## 2. Phạm vi

- **Được thêm:** `scripts/screen_vcp_daily.py`, `tests/test_screen_vcp_daily.py`.
- **Không được sửa:** mọi file có sẵn. Chỉ **import** (`Storage`, `TZ`, `is_trading_day`, `FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS`, `load_dotenv` của `scripts/_db_common.py`).
- **Không** dùng pandas/numpy: repo không có. Viết Python thuần; SMA dùng tổng trượt (deque), không tính lại từ đầu mỗi nến.
- Trước khi viết: `gitnexus_context` cho `read_daily_bars`. Sau khi viết: `gitnexus_detect_changes()`, dán kết quả. Ghi nhớ: file mới chưa vào index nên detect_changes có thể ra "none"; đó không có nghĩa là không có thay đổi.

---

## 3. Kiểm chứng (TDD: viết test trước, thấy đỏ, rồi mới viết code)

Test trên **chuỗi nến dựng tay**, không dùng DB.

1. **SMA và bộ lọc xu hướng:** chuỗi 260 nến dựng sẵn. Kiểm từng điều kiện trong 7 điều kiện bằng số tính tay. Làm hỏng từng điều kiện một thì bộ lọc phải trả `False`.
2. **Nền VCP:** ba đoạn có độ sâu 30% / 15% / 6% và volume giảm → đạt. Đổi `depth2 < depth3` → không đạt. `depth3 = 0,11` → không đạt. Volume S3 > S1 → không đạt.
3. **Phá vỡ:** `close[t] = P` → **không** (phải lớn hơn hẳn). `volume[t] = 1,49 ×` trung bình → không. `1,5 ×` → có.
4. **Thời gian nghỉ:** hai lần phá vỡ cách nhau 10 nến trên cùng mã → chỉ **1** sự kiện; cách nhau 21 nến → **2**.
5. **Giá trần theo sàn:** HOSE mở +6,95% → bỏ; +6,85% → giữ. HNX mở +9,95% → bỏ. Sàn lạ → dùng 7%.
6. **Công thức ròng:** vào 10.000, thoát 11.000 → tính tay `r_net` bằng đúng các hằng số import. Test phải **đỏ** nếu ai đó gõ tay 0,0025.
7. **Chống nhìn trộm tương lai — quan trọng nhất:** với một chuỗi có sự kiện tại `t`, **sửa tùy ý mọi nến sau `t`**. Việc phát hiện sự kiện tại `t`, bộ lọc xu hướng và nền **phải giữ nguyên**; chỉ mục tiêu được phép đổi. Lặp cho nhiều `t`.
8. **Múi giờ:** nến `ts = 2022-11-30 17:00 UTC` là ngày **01/12 VN**, nên **nằm ngoài** IS. Test phải đỏ nếu tính ngày theo UTC.
9. **Niêm phong:** đưa vào một nến ngày 2023-01-02 VN → **phải ném lỗi**.
10. **Đối chứng:** 3 mã cùng ngày, 1 là sự kiện → rổ đối chứng chỉ gồm 2 mã kia, và baseline bằng trung bình tính tay. Rổ dưới 5 mã → sự kiện bị loại khỏi phép so vượt trội.
11. **Bootstrap:** trên dữ liệu dựng tay, với `seed` cố định cho kết quả tất định. Việc gom khối theo **tháng dương lịch của `t` (giờ VN)** được kiểm bằng một ca sự kiện rơi vào ngày cuối tháng.
12. **Thiếu nến thoát:** sự kiện chỉ có 12 nến sau `t` → có `r_5`, `r_10`, **không** có `r_20`, và được đếm vào "bỏ vì thiếu dữ liệu".

### Kiểm thử phá hoại (bắt buộc)
Sao lưu **ra ngoài repo**. **Cấm** `git checkout`, `git restore`, `git stash`.
- Cho pivot gồm cả nến `t` → test 7 **hoặc** test 3 phải đỏ.
- Tính bộ lọc xu hướng tại `t` thay vì `t−1` → test 7 phải đỏ.
- Bỏ thời gian nghỉ → test 4 đỏ.
- Bỏ kiểm tra niêm phong → test 9 đỏ.
- Bỏ lọc giá trần → test 5 đỏ.
- Khôi phục, chạy lại, sạch. Báo tên test đỏ từng bước.

### Tổng
```
uv run pytest -m "not integration" -q     # mốc: 911 passed
uv run ruff check trading tests scripts
```

---

## 4. Chạy thật và đọc kết quả

`uv run python scripts/screen_vcp_daily.py`, **một lần**. In:
1. Số mã trong vũ trụ trước và sau khi loại; số nến rác bị bỏ.
2. Số sự kiện VCP trong IS, **theo từng năm** và **theo sàn**; số bị bỏ vì giá trần, vì thiếu dữ liệu, vì rổ đối chứng nhỏ.
3. Với `k = 5, 10, 20`: số sự kiện; trung bình và trung vị của `r_k` gộp, `r_k_net`, `baseline_k`, `excess_k`; tỷ lệ `excess_k > 0`.
4. Phép thử chính (`k = 20`): trung bình `excess_20`, khoảng tin cậy 95% từ bootstrap, `p`, và kết luận theo §1.7.
5. **Kiểm độ lệch:** tỷ trọng của 10 sự kiện `excess_20` lớn nhất trong tổng `excess_20`. Nếu 10 sự kiện đó chiếm hơn 50% tổng thì ghi rõ.
6. Thời gian chạy.

**Quy tắc đọc, không tự diễn giải thêm:**
- Không đạt §1.7 → ghi **"VCP dạng máy: KHÔNG có lợi thế so với cổ phiếu cùng xu hướng, sau chi phí"**. Đây là phép đo âm thứ bảy.
- Đạt §1.7 → **KHÔNG mở tập từ 2023**, **KHÔNG xây chiến lược**. Chỉ báo cáo. Claude quyết có mở tập niêm phong hay không; nếu mở thì mở **một lần** cho đúng phép thử chính.

---

## 5. Báo cáo cho Claude

1. GitNexus context và detect_changes.
2. Danh sách test; kiểm thử phá hoại (tên test đỏ từng bước).
3. Pytest và ruff.
4. **Nguyên văn** toàn bộ output của lần chạy thật; chạy hơn một lần thì dán tất cả kèm lý do.
5. Mọi quyết định nhỏ agent phải tự chọn vì brief chưa nói (ví dụ cách xử lý hai sự kiện cùng mã cùng ngày): liệt kê rõ từng cái.
6. Mọi điều thấy ngoài phạm vi: **báo cáo, không sửa.**

---

## 6. Ghi chú của planner — chưa giao

- **RS rating** (xếp hạng sức mạnh tương đối trong toàn thị trường) là một phần của phương pháp Minervini. Nó bị bỏ vì cần một bảng xếp hạng riêng tại từng thời điểm. Nếu đợt 99 dương, bước tiếp theo là thêm nó như **một** phép thử đăng ký trước, không phải như một biến thể để thử.
- **Thoát lệnh theo stop:** Minervini dùng cắt lỗ chặt (7–8%). Đợt này thoát theo thời gian cố định để đo **thông tin** của tín hiệu, không đo một hệ thống giao dịch. Hệ thống cụ thể chỉ đáng thiết kế nếu tín hiệu có thông tin.
