# Brief đợt 117 — Nạp lại nến 1h của đợt 114 bằng loader đã sửa, và biến phép đo bám theo mốc giờ thành script có test

Ngày giao: 28/09/2026. Base: main `fbddf06`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push, không đặt lệnh, không sửa `trading/`**.

## 0. Vì sao

Đợt 116 phát hiện `scripts/bingx_klines.py` từng có dòng `if len(raw_bars) < limit: break`, tức coi "trang trả về ít hơn `limit`" là dấu hiệu hết lịch sử. BingX **không** theo quy ước đó: với mã NC nó trả trang ngắn ngay giữa lúc lịch sử vẫn còn. Dòng đó đã bị bỏ trong commit `efdea3f`.

Hệ quả là **dữ liệu 1h của đợt 114 bị hụt, và kết luận của đợt 114 dựa trên dữ liệu hụt đó**. Claude kiểm trực tiếp lúc chiều 28/09: với mỗi mã, gọi một lần với `endTime` = (mốc nhỏ nhất đang có trong DB − 1ms) để xem có còn dữ liệu cũ hơn không.

| Mã | Nến 1h hiện có trong DB (từ ngày) | Còn dữ liệu cũ hơn? | Trang đó lùi tới |
|---|---|---|---|
| `NCCOGOLD2USD-USDT` | 4.779 (2026-02-03) | **còn 639 dòng** | 2025-12-23 |
| `NCSISP5002USD-USDT` | 2.753 (2026-04-28) | **còn 697 dòng** | 2026-03-17 |
| `NCSINASDAQ1002USD-USDT` | 2.753 (2026-04-28) | **còn 698 dòng** | 2026-03-17 |
| `NCSKAAPL2USD-USDT` | 3.592 (2026-03-17) | **còn 315 dòng** | 2026-02-03 |
| `NCSKNVDA2USD-USDT` | 3.592 (2026-03-17) | **còn 315 dòng** | 2026-02-03 |
| `NCCO1OILWTI2USD-USDT` | 2.838 (2026-04-28) | **còn 660 dòng** | 2026-03-17 |
| `NCCOXAG2USD-USDT` | 4.654 (2026-02-11) | **0 dòng** | — (đã đủ, 2026-02-11 đúng là ngày niêm yết) |

Sáu trên bảy mã bị hụt. Và chú ý các con số 639, 697, 698, 315, 660: **trang nào cũng ngắn hơn 1000**, nên loader cũ dừng ở đúng biên trang đầu tiên nó gặp, khác nhau tuỳ mã. Đó là lý do bảy mã dừng ở bảy ngày khác nhau chứ không phải vì BingX giữ lịch sử khác nhau.

**Hai điều Claude đã kiểm và agent KHÔNG cần kiểm lại:**
- **Nến 1d không bị hụt.** Mọi mã NC đều niêm yết dưới 13 tháng nên nến 1d dưới 400 cái, gói trong một trang. Nến 1d của EUR/USD lùi đúng tới ngày niêm yết 2025-08-27.
- **Nến 1h của crypto không bị hụt.** Cả 29 mã crypto đều bắt đầu đúng tại `2024-04-27 10:00 UTC`, mật độ 100%, không lỗ. Claude gọi thử với `endTime` trước mốc đó: BTC-USDT trả về **1 dòng**, tức không có gì cũ hơn. Đây là **hạn mức lưu trữ nến 1h của BingX**, không phải lỗi loader. Nên các phép đo BTC khung 1h ở đợt 105 và 106 **không bị ảnh hưởng**.

## 1. Phạm vi

| File | Được làm gì |
|---|---|
| `scripts/bingx_klines.py` | **Chỉ chạy**, không sửa. Đã sửa ở đợt 116. |
| `scripts/inventory_bingx_tradfi.py` | **Chỉ chạy**, không sửa. Nếu phải sửa mới chạy được thì **dừng và báo**. |
| `scripts/check_bingx_tracking_hourly.py` | **Mới.** Task B. |
| `tests/test_check_bingx_tracking_hourly.py` | **Mới.** |
| `docs/superpowers/research/2026-09-28-dot-117-nap-lai-nen-1h-va-do-bam-theo-moc-gio.md` | **Mới.** Báo cáo. |

**Không được đụng:**
- `trading/` — kể cả một dòng;
- `bars`, `bars_daily`, `bars_ext_daily`: **chỉ đọc**;
- `bars_crypto`: chỉ được ghi **qua `bingx_klines.py`**. Không `INSERT`/`UPDATE`/**`DELETE`** thủ công. `bingx_klines.py` dùng upsert theo khoá `(symbol, interval, ts)` nên nạp lại là thêm nến cũ vào, không xoá gì;
- các script khác, config, container, Task Scheduler, `.env`;
- **báo cáo đợt 114 cũ**: không sửa file cũ. Kết luận mới viết trong báo cáo đợt 117, có trỏ ngược lại.

**Cấm gọi endpoint có ký. Cấm đặt lệnh. Cấm in secret.**
**Niêm phong:** chỉ nạp và chỉ đọc đến hết **2026-08-31**.
**Sao lưu ra ngoài repo trước khi sửa file. Cấm `git checkout`, `git restore`, `git stash`.**

---

## Task A — Nạp lại nến 1h và viết lại kết luận đợt 114

### A1. Ghi trạng thái TRƯỚC khi nạp

```sql
SELECT symbol, interval, count(*), min(ts)::date, max(ts)::date
FROM bars_crypto WHERE symbol LIKE 'NC%' GROUP BY 1,2 ORDER BY 1,2;
```

→ **Kiểm chứng bằng:** dán kết quả. Đây là mốc để so sau khi nạp.

### A2. Nạp lại khung 1h cho đúng rổ đợt 114

```
uv run python scripts/bingx_klines.py --symbols NCCOGOLD2USD-USDT,NCCOXAG2USD-USDT,NCCO1OILWTI2USD-USDT,NCSISP5002USD-USDT,NCSINASDAQ1002USD-USDT,NCSKAAPL2USD-USDT,NCSKNVDA2USD-USDT --interval 1h --to 2026-08-31
```

→ **Kiểm chứng bằng:** dán nguyên văn output kèm số `calls` mỗi mã, rồi chạy lại truy vấn ở A1 và dán.

**Tiêu chí đạt của bước này:** với mỗi mã, `min(ts)` phải lùi về **đúng ngày niêm yết** dưới đây (lệch tối đa 1 ngày là được, vì giờ niêm yết trong ngày).

| Mã | `launchTime` (đợt 114 đã kiểm) |
|---|---|
| `NCCOGOLD2USD-USDT` | 2025-10-14 |
| `NCSKAAPL2USD-USDT` | 2025-11-13 |
| `NCSKNVDA2USD-USDT` | 2025-11-13 |
| `NCSISP5002USD-USDT` | 2025-11-26 |
| `NCSINASDAQ1002USD-USDT` | 2025-11-26 |
| `NCCOXAG2USD-USDT` | 2026-02-11 |
| `NCCO1OILWTI2USD-USDT` | 2026-03-09 |

Mã nào **không** lùi tới ngày niêm yết thì **dừng mã đó và báo**, kèm số `calls` và mốc dừng. Có thể là hạn mức lưu trữ thật, có thể là lỗi còn lại — **không tự kết luận cái nào**, hãy gọi thử một lần với `endTime` = (mốc nhỏ nhất mới − 1ms) rồi dán số dòng trả về làm bằng chứng.

**Không nạp lại khung 1d.** Claude đã xác minh 1d không bị hụt.

### A3. Kiểm kê lại, và viết lại kết luận đợt 114

Chạy `scripts/inventory_bingx_tradfi.py` và lập lại **bảng chính của đợt 114** trên dữ liệu mới:

`Mã | Niêm yết | Số nến 1d | Số nến 1h CŨ | Số nến 1h MỚI | Hồ sơ giờ 7×24 | Khoảng trống bất thường | Nến bẩn | Funding | Phí/ATR1h CŨ | Phí/ATR1h MỚI | Đủ đo khung giờ?`

Bốn điểm bắt buộc:

1. **Phải in cả cột CŨ và cột MỚI** cho số nến 1h và cho tỷ lệ phí/ATR1h. ATR ở đợt 114 tính trên cửa sổ bị hụt, nên con số đó có thể sai; đặt cạnh nhau để thấy sai bao nhiêu.
2. **Hồ sơ giờ 7×24 phải dựng lại** từ dữ liệu mới, không sao chép bảng cũ. Cửa sổ cũ chỉ vài tháng nên có thể đã bỏ sót phiên.
3. Áp lại **đúng hai ngưỡng của đợt 114**, không tự đổi:
   - đủ đo khung ngày: ít nhất **3 năm** nến 1d;
   - đủ đo khung giờ: ít nhất **1 năm** nến 1h, **và** dưới 1% khoảng trống bất thường.
4. Nói rõ **mã nào đổi kết luận** so với đợt 114. Dự kiến của Claude: vàng từ "1h chỉ từ 02/2026" có thể thành gần một năm đầy đủ, tức **có thể** chạm ngưỡng khung giờ. Đây là dự kiến cần kiểm, **không phải kết quả mong muốn**. Nếu số liệu nói không đạt thì báo không đạt.

**Không kết luận gì về lợi nhuận, chiến lược, hay việc có nên giao dịch.** Chỉ kết luận dữ liệu **đủ** hay **không đủ** để đo.

### A4. Báo cáo-thêm, không sửa

`bars_crypto` đang chứa dữ liệu **quá mốc niêm phong 2026-09-01**: crypto tới 2026-09-02, riêng BTC và ETH tới 2026-09-08. Agent **chỉ liệt kê** mã nào có bao nhiêu dòng sau 2026-08-31, ở cả hai khung. **Không xoá.** Claude quyết xử lý sau.

---

## Task B — Biến phép đo bám theo mốc giờ thành script có test

Ở phần audit đợt 116, Claude đo bằng SQL rời trong terminal. Việc đo lại được thì mới tin được, nên phải thành script.

### B1. Việc script phải làm

`scripts/check_bingx_tracking_hourly.py`, chỉ đọc `bars_crypto` và `bars_ext_daily`.

Với mỗi cặp (mã BingX, nguồn ngoài):

| Cặp | Nguồn ngoài |
|---|---|
| `NCFXEUR2USD-USDT` | `FRB_H10` / `EURUSD` |
| `NCFXEUR2USD-USDT` | `ECB` / `EURUSD` |
| `NCFXUSD2JPY-USDT` | `FRB_H10` / `USDJPY` |

Với **từng giờ UTC từ 0 đến 23**:
1. Lấy chuỗi `close` của nến 1h tại đúng giờ đó, mỗi ngày một điểm.
2. Ghép theo ngày với chuỗi ngoài. **Ghép ngày trước, rồi mới tính lợi suất trên các ngày đã khớp** — thứ tự này quan trọng, làm ngược cho ra số khác (Claude đã tự sai một lần: 0,6711 thay vì 0,7345).
3. Tính: số ngày khớp, tương quan Pearson của lợi suất ngày, tracking error năm hoá, basis trung vị và P5–P95.

Rồi in **bảng 24 dòng** cho mỗi cặp, sắp theo tương quan giảm dần, và nêu giờ tốt nhất.

### B2. Mốc phải tái lập được — đây là tiêu chí đạt

Script phải cho ra **đúng** các số Claude đã đo (sai số ±0,0005 ở tương quan):

| Cặp | Giờ UTC | n | Tương quan |
|---|---|---|---|
| EUR/USD × FRB_H10 | **16** | 248 | **0,9776** |
| EUR/USD × FRB_H10 | 15 | 251 | 0,9727 |
| EUR/USD × FRB_H10 | 17 | 250 | 0,9390 |
| USD/JPY × FRB_H10 | **16** | 247 | **0,9907** |
| USD/JPY × FRB_H10 | 15 | 250 | 0,9874 |
| EUR/USD × ECB | **11** | 256 | **0,9370** |
| EUR/USD × ECB | 12 | 256 | 0,9323 |

Không ra đúng thì **dừng và báo lệch bao nhiêu**, đừng chỉnh cho khớp. Một trong hai bên sai, và phải tìm ra bên nào.

### B3. Test

Hàm thuần, mỗi hàm một test có **ví dụ tính tay ghi rõ trong test**:
- lấy chuỗi theo giờ UTC;
- ghép theo ngày;
- tương quan Pearson — tính tay trên 4–5 điểm, không gọi `numpy` để dựng kỳ vọng;
- tracking error năm hoá — nói rõ dùng `sqrt(252)` và vì sao;
- basis và phân vị.

**Bốn phép phá thử bắt buộc**, mỗi phép phải làm ít nhất một test **đỏ**. Dán output đỏ của cả bốn:
1. Lấy giờ `h+1` thay vì `h` → đỏ.
2. Tính lợi suất trên chuỗi thô **trước** khi ghép ngày → đỏ.
3. Đổi `sqrt(252)` thành `252` → đỏ.
4. Đổi trung vị basis thành trung bình → đỏ.

Nếu phép nào mà test vẫn xanh thì **test đó yếu**: siết lại rồi phá lại, và **ghi cả lần yếu lẫn lần đã siết**. Đợt 116 có một test ATR mù đúng kiểu này (15 nến giống hệt nhau nên cửa sổ nào cũng ra 2,0%), Claude phát hiện bằng phá thử. Đừng để lặp lại.

**Cấm dựng `expected` bằng cách viết lại công thức của hàm trong thân test.** Ghim số literal đã tính tay. Đợt 116 mắc lỗi này ở hai test và Claude đã phải sửa.

→ **Kiểm chứng bằng:**
```
uv run pytest tests/test_check_bingx_tracking_hourly.py -v
uv run ruff check trading tests scripts/check_bingx_tracking_hourly.py
uv run pytest -m "not integration" -q
```
Dán nguyên văn cả ba. Suite hiện tại là **1.212 pass**; con số mới phải là 1.212 cộng số test agent thêm.

---

## 2. Báo cáo cho Claude

Theo thứ tự:

1. **Kết luận hai dòng:** dòng 1 — mã nào đổi kết luận đợt 114 và đổi thế nào; dòng 2 — script Task B có tái lập đúng bảng ở B2 hay không.
2. Task A: output A1, A2, A3 nguyên văn, kèm bảng chính CŨ/MỚI và danh sách A4.
3. Task B: bảng 24 dòng cho cả ba cặp, output pytest và ruff, bốn lần phá thử.
4. **Mọi điều bất thường**, kể cả cảnh báo nhỏ, kể cả điều agent thấy mà brief không hỏi. Dead code hay lỗi ngoài phạm vi thì **báo lại, không tự sửa**.
5. **Danh sách những gì agent KHÔNG kiểm được** và lý do. Mục này không được để trống bằng một câu "không có".

**Cấm trong báo cáo:**
- nói chủ dự án đã xác nhận điều gì khi chủ dự án chưa nói (lỗi đã xảy ra ở đợt 111);
- khẳng định phủ định kiểu "không có X" khi chỉ grep mà chưa mở nguồn kiểm;
- bất kỳ câu nào về lợi nhuận, chiến lược, hay việc có nên giao dịch;
- hằng số phí, chu kỳ funding, ngày niêm yết **không có URL nguồn hoặc phản hồi API kèm theo**.

## 3. GitNexus

Đợt này **không sửa symbol đang tồn tại**: Task A chỉ chạy script, Task B chỉ tạo file mới. Không cần `gitnexus_impact`.

Vẫn phải:
- `gitnexus_query` để chắc chưa có script nào đã đo bám theo mốc giờ — trùng thì **báo lại, đừng viết trùng**;
- `gitnexus_detect_changes` trước khi báo cáo, dán output. Thấy symbol cũ bị ảnh hưởng thì **dừng và báo**.

Trong phiên 28/09 của Claude, MCP `gitnexus` lỗi `CONNECT_TIMEOUT`. Index cũng đang **stale** (đợt 116 báo `Indexed commit: e3fa18a`). Nếu agent gặp lỗi tương tự thì ghi vào mục §2.5 và thay bằng `grep` có ghi rõ câu lệnh — **không im lặng bỏ qua**. Vẫn **không** tự chạy `npx gitnexus analyze --force`.

Kết thúc bằng đúng câu: "Tôi không commit, không push, không đặt lệnh, không gọi endpoint có ký, không sửa `trading/`, không xoá dòng nào trong `bars_crypto`, không nạp dữ liệu từ 2026-09-01, và mọi hằng số đều có nguồn."
