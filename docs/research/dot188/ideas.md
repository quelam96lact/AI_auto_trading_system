# Danh sách 6 ý tưởng nghiên cứu đa khung thời gian (Đợt 188)

- Ngày đăng ký: 19/10/2026.
- Ngân sách: 6 ý tưởng, tổng cộng 151 cấu hình EA (ngân sách trần 400).
- Nguyên tắc: Không nhìn trước nến chưa đóng (`align_higher` với `close_time <= lower_bar.close_time`), khớp tại `open[t+1]`, giữ $\ge 3$ phiên với cổ phiếu, chi phí đầy đủ.

---

## 1. Ý tưởng 1: `STK_WK_TREND_PULLBACK` (Cổ phiếu VN)

1. **Cơ chế kinh tế:** Dòng tiền tổ chức tạo ra xu hướng tăng bền vững kéo dài nhiều tháng trên khung tuần; các đợt sụt giảm ngắn hạn khung ngày phản ánh tâm lý chốt lời hoảng loạn từ nhà đầu tư nhỏ lẻ. Khi chỉ số RSI ngày rơi vào vùng quá bán sâu trong khi xu hướng tuần vẫn được bảo toàn (Close tuần > SMA tuần), lực cầu tổ chức quay lại đẩy giá phục hồi.
2. **Luật vào/ra:**
   - **Vào lệnh:** Tại close ngày $t$, nến tuần đóng gần nhất có `weekly_close > weekly_sma(w_period)`. Khung ngày $t$ có `daily_rsi(rsi_len) < rsi_thresh`. Mua tại open ngày $t+1$ nếu `entry_status == 'ok'`.
   - **Thoát lệnh:** Sau khi giữ tối thiểu 3 phiên (T+2), thoát tại open ngày tiếp theo khi `daily_close > daily_sma(10)` hoặc sau tối đa 15 phiên ngày.
   - **Điểm ưu tiên (score):** `(rsi_thresh - daily_rsi)` (quá bán càng sâu ưu tiên càng cao).
3. **Khác các họ đã âm:** Đợt 173 (Pullback thuần ngày) chỉ dùng EMA/SMA ngày nên hay mua dò đáy trong các downtrend lớn của thị trường. Ý tưởng này bắt buộc nến tuần đã đóng xác nhận xu hướng tăng trung hạn trước khi cho phép khung ngày tìm điểm vào.
4. **Lưới tham số (27 cấu hình):**
   - `w_period` (tuần): `[10, 20, 30]`
   - `rsi_len` (ngày): `[3, 5, 7]`
   - `rsi_thresh`: `[20, 25, 30]`
5. **Thị trường:** Cổ phiếu VN (Long-only).

---

## 2. Ý tưởng 2: `STK_WK_VOL_BREAKOUT` (Cổ phiếu VN)

1. **Cơ chế kinh tế:** Hiện tượng co hẹp biến động khung tuần (Narrow Range Week / Volatility Squeeze) phản ánh sự cạn kiệt nguồn cung bán tháo và quá trình tích lũy kín đáo; khi khung ngày kích hoạt phá vỡ đỉnh kèm khối lượng tăng vọt, dòng tiền mới bắt đầu bùng nổ xu hướng mới.
2. **Luật vào/ra:**
   - **Vào lệnh:** Nến tuần đóng gần nhất có độ co hẹp biến động `(weekly_high - weekly_low) / weekly_close < vol_thresh`. Khung ngày $t$ có `close > max(high của n_days trước)` và `volume > 1.3 * sma_volume(20)`. Mua tại open $t+1$ nếu `entry_status == 'ok'`.
   - **Thoát lệnh:** Sau $\ge 3$ phiên, thoát tại open ngày tiếp theo khi nến ngày đóng thủng `min(low của exit_days trước)`.
   - **Điểm ưu tiên (score):** `daily_volume / sma_volume(20)`.
3. **Khác các họ đã âm:** Đợt 175 (Donchian breakout thuần ngày) bị dính whipsaw liên tục ở thị trường đi ngang vì mua mọi đỉnh Donchian 20 ngày. Ở đây chỉ mua khi khung tuần trước đó đã co hẹp biến động cực đại (hạn chế mua đuổi đỉnh sau một nhịp tăng dài).
4. **Lưới tham số (27 cấu hình):**
   - `vol_thresh`: `[0.05, 0.07, 0.09]`
   - `n_days`: `[15, 20, 25]`
   - `exit_days`: `[5, 10, 15]`
5. **Thị trường:** Cổ phiếu VN (Long-only).

---

## 3. Ý tưởng 3: `STK_MN_TREND_WK_MOM` (Cổ phiếu VN)

1. **Cơ chế kinh tế:** Xu hướng khung tháng (Monthly Regime) đại diện cho chu kỳ vĩ mô và tăng trưởng kinh doanh cơ bản; khi khung tháng đang trong xu thế tăng (`monthly_close > monthly_sma(m_len)`), các đợt bứt phá động lượng trên khung tuần (`weekly_close > weekly_close[k_weeks] * (1 + mom_thresh)`) đánh dấu sự xác nhận tham gia của dòng vốn tổ chức lớn.
2. **Luật vào/ra:**
   - **Vào lệnh:** Nến tháng đóng gần nhất có `monthly_close > monthly_sma(m_len)`. Nến tuần đóng gần nhất có `weekly_close / weekly_close[k_weeks] - 1.0 > mom_thresh`. Mua tại open ngày $t+1$ đầu tiên của tuần tiếp theo nếu `entry_status == 'ok'`.
   - **Thoát lệnh:** Sau $\ge 3$ phiên, thoát khi nến ngày đóng thủng `sma_daily(20)` hoặc sau tối đa 30 phiên ngày.
   - **Điểm ưu tiên (score):** Tỷ lệ tăng động lượng tuần `(weekly_close / weekly_close[k_weeks] - 1.0)`.
3. **Khác các họ đã âm:** Khung ngày có quá nhiều nhiễu giá (noise) dẫn đến các phép đo SMA/momentum ngày thất bại. Sự kết hợp giữa bộ lọc tháng đóng (lọc chu kỳ) và xung lực tuần giúp giảm tần suất giao dịch và loại bỏ các bẫy giá giả ngắn hạn.
4. **Lưới tham số (27 cấu hình):**
   - `m_len` (tháng): `[6, 9, 12]`
   - `k_weeks` (tuần): `[2, 4, 6]`
   - `mom_thresh`: `[0.02, 0.04, 0.06]`
5. **Thị trường:** Cổ phiếu VN (Long-only).

---

## 4. Ý tưởng 4: `CRY_1D_TREND_4H_PULLBACK` (Crypto BingX Perp)

1. **Cơ chế kinh tế:** Thị trường phái sinh crypto 24/7 có tính xu hướng quán tính cao trên khung ngày (1D Trend). Trong khi xu hướng ngày tiếp diễn, các đợt đòn bẩy quá mức trên khung 4h thường gây ra chuỗi thanh lý cưỡng bức ngắn hạn (liquidation cascades) đẩy RSI 4h vào vùng quá mua/quá bán cực đoan; mở vị thế theo xu hướng ngày khi lực ép thanh lý 4h cạn kiệt mang lại biên an toàn cao.
2. **Luật vào/ra:**
   - **Vào lệnh Long:** Nến 1d đóng gần nhất có `1d_close > 1d_sma(d_period)`. Nến 4h đóng gần nhất có `rsi_4h(14) < rsi_low`. Mở Long tại open 1h $t+1$.
   - **Vào lệnh Short:** Nến 1d đóng gần nhất có `1d_close < 1d_sma(d_period)`. Nến 4h đóng gần nhất có `rsi_4h(14) > 100 - rsi_low`. Mở Short tại open 1h $t+1$.
   - **Thoát lệnh:** Thoát tại open 1h tiếp theo khi nến 4h đóng chạm `sma_4h(exit_len)` hoặc sau tối đa 24 nến 1h.
   - **Điểm ưu tiên (score):** Độ lệch RSI so với ngưỡng (`rsi_low - rsi_4h` với Long, `rsi_4h - (100 - rsi_low)` với Short).
3. **Khác các họ đã âm:** Các đợt 183/184/187 dùng footprint order flow micro giây bị trượt giá và nhiễu vi mô. Ý tưởng này neo theo cấu trúc nến 1d và 4h đóng chuẩn xác, có tính thanh lý rõ rệt.
4. **Lưới tham số (27 cấu hình):**
   - `d_period` (ngày): `[15, 20, 30]`
   - `rsi_low`: `[25, 30, 35]`
   - `exit_len` (nến 4h): `[10, 15, 20]`
5. **Thị trường:** Crypto Perpetual BingX (Long/Short).

---

## 5. Ý tưởng 5: `CRY_4H_VOL_BREAKOUT` (Crypto BingX Perp)

1. **Cơ chế kinh tế:** Sự co thắt biến động dải Bollinger trên khung 4h đi kèm đợt bung dải biên độ mạnh là tín hiệu của các cú hích tin tức và dòng vốn dịch chuyển; đi theo đà phá vỡ này khi khung ngày đồng thuận xu hướng giúp nắm bắt những đợt tăng/giảm mạnh mẽ nhất của crypto.
2. **Luật vào/ra:**
   - **Vào lệnh Long:** Nến 1d đóng gần nhất có `close_1d > ema_1d(trend_len)`. Nến 4h đóng gần nhất có `close_4h > upper_bb_4h(bb_len, bb_std)`. Mở Long tại open 1h $t+1$.
   - **Vào lệnh Short:** Nến 1d đóng gần nhất có `close_1d < ema_1d(trend_len)`. Nến 4h đóng gần nhất có `close_4h < lower_bb_4h(bb_len, bb_std)`. Mở Short tại open 1h $t+1$.
   - **Thoát lệnh:** Thoát tại open 1h tiếp theo khi nến 4h đóng chạm dải giữa `sma_4h(bb_len)` hoặc sau tối đa 36 nến 1h.
   - **Điểm ưu tiên (score):** Tỷ lệ vượt dải BB của nến 4h.
3. **Khác các họ đã âm:** Không cố gắng bắt đỉnh đáy đảo chiều; kết hợp bộ lọc xu hướng 1d đóng để loại bỏ các đợt phá vỡ ngược xu hướng vĩ mô.
4. **Lưới tham số (27 cấu hình):**
   - `trend_len` (ngày): `[10, 20, 30]`
   - `bb_len` (nến 4h): `[15, 20, 25]`
   - `bb_std`: `[1.8, 2.0, 2.2]`
5. **Thị trường:** Crypto Perpetual BingX (Long/Short).

---

## 6. Ý tưởng 6: `STK_WK_DONCHIAN_CHANNEL` (Cổ phiếu VN)

1. **Cơ chế kinh tế:** Khung tuần của thị trường chứng khoán phản ánh đầy đủ chu kỳ dòng tiền trung hạn và loại trừ hoàn toàn các biến động giật cục trong ngày/trong tuần do cơ cấu danh mục hoặc thao túng phiên ATC. Mua phá vỡ kênh Donchian khung tuần của cổ phiếu có thanh khoản tốt là một chiến lược xu hướng kinh điển.
2. **Luật vào/ra:**
   - **Vào lệnh:** Nến tuần đóng gần nhất có `weekly_close > max(weekly_high của n_weeks trước)`. Mua tại open ngày $t+1$ đầu tiên của tuần tiếp theo nếu `entry_status == 'ok'`.
   - **Thoát lệnh:** Sau $\ge 3$ phiên, thoát tại open ngày tiếp theo khi nến tuần đóng gần nhất thủng `min(weekly_low của exit_weeks trước)`.
   - **Điểm ưu tiên (score):** `(weekly_close / max_high - 1.0)`.
3. **Khác các họ đã âm:** Đợt 175 (Donchian breakout khung ngày) thất bại vì khung ngày xuất hiện quá nhiều bẫy giá trong các giai đoạn tích lũy đi ngang. Chuyển toàn bộ chu kỳ Donchian sang nến tuần đóng giúp lệnh có thời gian tích lũy trung hạn và chỉ vào khi xu hướng tuần thực sự xác lập.
4. **Lưới tham số (16 cấu hình):**
   - `n_weeks`: `[10, 15, 20, 25]`
   - `exit_weeks`: `[5, 8, 10, 12]`
5. **Thị trường:** Cổ phiếu VN (Long-only).
