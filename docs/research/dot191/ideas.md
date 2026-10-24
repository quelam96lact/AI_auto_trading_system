# Danh Mục Ý Tưởng Khám Phá Khối Ngoại Chốt Lời +10% (Brief 191)

Tài liệu đăng ký trước các ý tưởng giao dịch theo quy định Brief 191 §4.1.
Toàn bộ ý tưởng dùng chung luật thoát tại §3.2 và universe thanh khoản GTGD 20 phiên $\ge 10$ tỷ VND tại §3.3.
Không dùng học máy, không tối ưu riêng cho từng mã, một luật áp dụng toàn thị trường, chỉ mua (long-only).

---

## 1. IDEA1_FOREIGN_ACCUMULATION_STREAK (Chuỗi gom ròng khối ngoại liên tiếp)

1. **Cơ chế kinh tế:** Các định chế tài chính nước ngoài (quỹ mở, quỹ hưu trí, ETF) khi giải ngân vào cổ phiếu vốn hoá lớn thường tích luỹ theo lô lệnh trong nhiều phiên liên tiếp, tạo lực cầu hấp thụ bền vững giúp đẩy giá cổ phiếu tăng bứt phá đạt mục tiêu lợi nhuận $\ge +10\%$.
2. **Luật vào lệnh:**
   - Tại ngày tín hiệu $t$: Mã đạt lọc GTGD 20 phiên $\ge 10$ tỷ VND.
   - Khối ngoại mua ròng liên tiếp ít nhất $K$ phiên kết thúc tại $t$ (`net_val > 0` cho mọi phiên từ $t - K + 1$ đến $t$).
   - Tổng giá trị mua ròng $K$ phiên đó chiếm tỷ trọng đáng kể trong thanh khoản:
     $$\frac{\sum_{i=t-K+1}^t \text{net\_val}_i}{\sum_{i=t-K+1}^t \text{gtgd}_i} \ge \text{min\_ratio}$$
   - Khớp mua tại `open` phiên $t+1$ nếu `entry_status == "ok"`.
3. **Vì sao khối ngoại là lõi:** Tín hiệu hoàn toàn phụ thuộc vào chuỗi mua ròng liên tục của dòng tiền ngoại và tỷ trọng mua ròng so với toàn thị trường, không dựa vào chỉ báo kỹ thuật giá nến/MA như các họ đã âm.
4. **Lưới tham số trước khi chạy (3 tham số, tính cả `tp`):**
   - $K \in \{3, 5\}$ (số phiên mua ròng liên tiếp)
   - $\text{min\_ratio} \in \{0.08, 0.15, 0.25\}$ (tỷ lệ mua ròng / thanh khoản)
   - $tp \in \{0.10, 0.15, 0.20\}$
   - Tổng cấu hình EA: $2 \times 3 \times 3 = 18$ cấu hình.
5. **Điểm ưu tiên:** $\frac{\sum_{i=t-K+1}^t \text{net\_val}_i}{\sum_{i=t-K+1}^t \text{gtgd}_i}$ cao hơn ưu tiên trước.

---

## 2. IDEA2_FOREIGN_CROSS_SECTION_TOP (Top mua ròng cắt ngang so với thanh khoản)

1. **Cơ chế kinh tế:** Vào mỗi phiên, những cổ phiếu dẫn đầu toàn thị trường về tỷ lệ gom của khối ngoại trong 20 phiên gần nhất là những mã có sự bảo trợ vốn mạnh nhất, có xác suất cao nhất bứt phá tạo sóng tăng lớn $\ge +10\%$.
2. **Luật vào lệnh:**
   - Tại ngày tín hiệu $t$: Lọc universe gồm tất cả các mã đạt lọc GTGD 20 phiên $\ge 10$ tỷ VND.
   - Tính tỷ lệ gom 20 phiên:
     $$\text{cum\_ratio}_{20} = \frac{\sum_{i=t-19}^t \text{net\_val}_i}{\sum_{i=t-19}^t \text{gtgd}_i}$$
   - Điều kiện: $\text{cum\_ratio}_{20} \ge \text{threshold}$ VÀ nằm trong top $Q$ mã có tỷ lệ gom cao nhất toàn universe tại ngày $t$.
   - Đồng thời ngày $t$ khối ngoại vẫn duy trì mua ròng (`net_val > 0`).
   - Khớp mua tại `open` phiên $t+1$ nếu `entry_status == "ok"`.
3. **Vì sao khối ngoại là lõi:** Quyết định vào lệnh căn cứ trên xếp hạng tương quan sức mua ngoại trên toàn bộ rổ cổ phiếu thanh khoản.
4. **Lưới tham số trước khi chạy (3 tham số, tính cả `tp`):**
   - $Q \in \{5, 10\}$ (top mã dẫn đầu)
   - $\text{threshold} \in \{0.05, 0.10, 0.15\}$
   - $tp \in \{0.10, 0.15, 0.20\}$
   - Tổng cấu hình EA: $2 \times 3 \times 3 = 18$ cấu hình.
5. **Điểm ưu tiên:** $\text{cum\_ratio}_{20}$ cao hơn ưu tiên trước.

---

## 3. IDEA3_FOREIGN_DIVERGENCE_DIP (Phân kỳ: Ngoại gom ròng trong nhịp điều chỉnh)

1. **Cơ chế kinh tế:** Khi cổ phiếu chịu áp lực điều chỉnh ngắn hạn (giá giảm) nhưng khối ngoại tranh thủ giá chiết khấu để gom ròng mạnh, đây là tín hiệu gom thông minh (smart money accumulation) dự báo đợt hồi phục mạnh sau khi áp lực bán cạn kiệt.
2. **Luật vào lệnh:**
   - Tại ngày tín hiệu $t$: Mã đạt lọc GTGD 20 phiên $\ge 10$ tỷ VND.
   - Giá cổ phiếu trong 10 phiên gần nhất giảm: $\text{close}_t / \text{close}_{t-10} - 1.0 \le -\text{drop\_rate}$.
   - Nhưng khối ngoại trong 10 phiên đó mua ròng tích luỹ:
     $$\frac{\sum_{i=t-9}^t \text{net\_val}_i}{\sum_{i=t-9}^t \text{gtgd}_i} \ge \text{foreign\_ratio}$$
   - Khớp mua tại `open` phiên $t+1$ nếu `entry_status == "ok"`.
3. **Vì sao khối ngoại là lõi:** Phân kỳ giữa chiều giảm của giá và chiều tăng vốn gom của khối ngoại; khối ngoại làm điều kiện bảo chứng cho việc bắt đáy, tránh rơi vào bẫy giá xuống.
4. **Lưới tham số trước khi chạy (3 tham số, tính cả `tp`):**
   - $\text{drop\_rate} \in \{0.03, 0.05, 0.08\}$
   - $\text{foreign\_ratio} \in \{0.05, 0.10, 0.15\}$
   - $tp \in \{0.10, 0.15, 0.20\}$
   - Tổng cấu hình EA: $3 \times 3 \times 3 = 27$ cấu hình.
5. **Điểm ưu tiên:** $\text{foreign\_ratio}$ cao hơn ưu tiên trước.

---

## 4. IDEA4_FOREIGN_REVERSAL_SURGE (Khối ngoại đảo chiều từ bán ròng sang mua đột biến)

1. **Cơ chế kinh tế:** Một cổ phiếu bị khối ngoại bán ròng miệt mài trong 10 phiên trước đó đột ngột đổi chiều sang mua ròng với khối lượng lớn bất thường (do tái cơ cấu quỹ, tin tức nội bộ tích cực, hoặc dòng vốn mới), tạo bước ngoặt đảo chiều tâm lý thị trường.
2. **Luật vào lệnh:**
   - Tại ngày tín hiệu $t$: Mã đạt lọc GTGD 20 phiên $\ge 10$ tỷ VND.
   - 10 phiên trước đó (từ $t-10$ đến $t-1$), tổng giá trị ròng của khối ngoại là bán ròng: $\sum_{i=t-10}^{t-1} \text{net\_val}_i < 0$.
   - Tại ngày $t$: Khối ngoại mua ròng đột biến với $\text{net\_val}_t / \text{gtgd}_t \ge \text{spike\_ratio}$ VÀ $\text{net\_val}_t \ge M \times |\text{avg\_sell}_{t-10..t-1}|$.
   - Khớp mua tại `open` phiên $t+1$ nếu `entry_status == "ok"`.
3. **Vì sao khối ngoại là lõi:** Tín hiệu kích hoạt trực tiếp từ sự đổi chiều đột ngột 180 độ của dòng tiền ngoại sau chuỗi bán tháo.
4. **Lưới tham số trước khi chạy (3 tham số, tính cả `tp`):**
   - $\text{spike\_ratio} \in \{0.10, 0.15, 0.20\}$
   - $M \in \{1.5, 2.0\}$ (tỷ lệ mua phiên t so với trung bình bán 10 phiên trước)
   - $tp \in \{0.10, 0.15, 0.20\}$
   - Tổng cấu hình EA: $3 \times 2 \times 3 = 18$ cấu hình.
5. **Điểm ưu tiên:** $\text{net\_val}_t / \text{gtgd}_t$ cao hơn ưu tiên trước.

---

## 5. IDEA5_FOREIGN_ROOM_EXHAUSTION (Cạn room ngoại: Khối ngoại tranh mua room còn lại)

1. **Cơ chế kinh tế:** Khi cổ phiếu cơ bản tốt sắp kín room sở hữu nước ngoài (foreign ownership limit), dòng tiền ngoại thường có xu hướng tranh mua quyết liệt lượng cổ phiếu room còn lại trước khi room về 0. Lực mua này đẩy giá tăng dốc.
2. **Luật vào lệnh:**
   - Tại ngày tín hiệu $t$: Mã đạt lọc GTGD 20 phiên $\ge 10$ tỷ VND.
   - Có dữ liệu `current_room` hợp lệ tại $t$ và $t-10$.
   - Room còn lại giảm mạnh: $\text{current\_room}_t \le \text{current\_room}_{t-10} \times (1 - \text{room\_drop\_pct})$.
   - Khối ngoại mua ròng tại ngày $t$: $\text{net\_val}_t / \text{gtgd}_t \ge \text{min\_flow\_ratio}$.
   - Khớp mua tại `open` phiên $t+1$ nếu `entry_status == "ok"`.
3. **Vì sao khối ngoại là lõi:** Khai thác thuộc tính đặc thù `current_room` và áp lực tranh mua của khối ngoại khi room ngoại cạn kiệt.
4. **Lưới tham số trước khi chạy (3 tham số, tính cả `tp`):**
   - $\text{room\_drop\_pct} \in \{0.10, 0.20, 0.30\}$
   - $\text{min\_flow\_ratio} \in \{0.05, 0.10\}$
   - $tp \in \{0.10, 0.15, 0.20\}$
   - Tổng cấu hình EA: $3 \times 2 \times 3 = 18$ cấu hình.
5. **Điểm ưu tiên:** Tốc độ giảm room $\frac{\text{current\_room}_{t-10} - \text{current\_room}_t}{\text{current\_room}_{t-10}}$ cao hơn ưu tiên trước.

---

### Tổng Kết Lưới Khám Phá EA

| Ý tưởng | Số tham số | Lưới tham số | Số cấu hình EA |
|---|---|---|---|
| Idea 1: Foreign Accumulation Streak | 3 | $K \in \{3, 5\}$, $\text{ratio} \in \{0.08, 0.15, 0.25\}$, $tp \in \{0.10, 0.15, 0.20\}$ | 18 |
| Idea 2: Foreign Cross-Section Top | 3 | $Q \in \{5, 10\}$, $\text{threshold} \in \{0.05, 0.10, 0.15\}$, $tp \in \{0.10, 0.15, 0.20\}$ | 18 |
| Idea 3: Foreign Divergence Dip | 3 | $\text{drop} \in \{0.03, 0.05, 0.08\}$, $\text{ratio} \in \{0.05, 0.10, 0.15\}$, $tp \in \{0.10, 0.15, 0.20\}$ | 27 |
| Idea 4: Foreign Reversal Surge | 3 | $\text{spike} \in \{0.10, 0.15, 0.20\}$, $M \in \{1.5, 2.0\}$, $tp \in \{0.10, 0.15, 0.20\}$ | 18 |
| Idea 5: Foreign Room Exhaustion | 3 | $\text{drop} \in \{0.10, 0.20, 0.30\}$, $\text{ratio} \in \{0.05, 0.10\}$, $tp \in \{0.10, 0.15, 0.20\}$ | 18 |
| **Tổng cộng** | | | **99 cấu hình** (≤ 400 trần) |
