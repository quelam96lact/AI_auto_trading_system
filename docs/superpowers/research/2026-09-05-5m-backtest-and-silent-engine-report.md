# Báo cáo Nghiên cứu: Chốt chặn Engine Câm (Gói X) & Đo lường Khung 5 Phút (Gói Y)

Ngày thực hiện: **05/09/2026 (Thứ Bảy)**.  
Kế hoạch thực thi: [`docs/superpowers/plans/2026-09-05-danh-gia-go-live-va-plan-ton-dong.md`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/docs/superpowers/plans/2026-09-05-danh-gia-go-live-va-plan-ton-dong.md).

---

## 1. PHÁT HIỆN CỐT LÕI: ENGINE ĐANG CÂM CHIỀU MUA DO LỆCH HỆ QUY CHIẾU THAM SỐ

### 1.1. Hiện tượng & Bản chất
- Thuộc tính `min_avg_value_20 = 2_000_000_000.0` trong `OctopusPullbackStrategy` được thiết kế theo ý nghĩa: *"Bình quân giá trị giao dịch 20 **phiên ngày** $\ge 2$ tỷ VND"* (đo trên `bars_daily`).
- Tuy nhiên, trong môi trường vận hành thực tế (`trading/engine/main.py:279`), engine nhận dòng dữ liệu bar **5 phút** từ NATS.
- Với bar 5 phút, phép tính rolling 20 bar chuyển thành *"Bình quân giá trị giao dịch 20 **bar 5 phút** (≈100 phút) $\ge 2$ tỷ VND"*. Ngưỡng này cao gấp **~78 lần** so với giá trị giao dịch thực tế của các cổ phiếu cơ sở trong 100 phút.

### 1.2. Bằng chứng Thực nghiệm trên Dữ liệu DB `bars` (3 mã đang cấu hình)

Chạy kiểm tra với [`scripts/check_silent_engine.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/check_silent_engine.py):

```
=========================================================================================================
BÁO CÁO CHỐT CHẶN 'ENGINE CÂM' (GÓI X) — Chiến lược: OctopusPullbackStrategy
=========================================================================================================
Mã       | Số bar 5m  | BQ giá trị/bar     | Cổng mở (bar / %)    | Tín hiệu (Bull/Bear)   | Trạng thái
---------------------------------------------------------------------------------------------------------
HII      | 3,211      | 80,025,634 đ       | 0 bar (0.0%)         | 0 bull / 0 bear        | [CRITICAL_SILENT] Cổng thanh khoản đóng 100% (0 bar mở)
IJC      | 4,719      | 334,127,305 đ      | 24 bar (0.5%)        | 0 bull / 0 bear        | [WARN_NO_BULL] 0 tín hiệu bull (cổng mở 24 bar, 0.5%)
AAA      | 4,597      | 152,980,117 đ      | 0 bar (0.0%)         | 0 bull / 0 bear        | [CRITICAL_SILENT] Cổng thanh khoản đóng 100% (0 bar mở)
=========================================================================================================
```

- **HII (3.211 bar)** và **AAA (4.597 bar)**: Cổng thanh khoản đóng **100% (0 bar mở)**.
- **IJC (4.719 bar)**: Cổng chỉ mở **24 bar (0,5%)** và không bar nào đủ điều kiện hình thành tín hiệu `bull`.
- $\rightarrow$ **Kết luận**: Engine hiện tại **không thể mua bất kỳ cổ phiếu nào** khi chạy với cấu hình mặc định.

---

## 2. GÓI X: CHỐT CHẶN TỰ ĐỘNG "ENGINE CÂM" (SILENT ENGINE GUARD)

Đã hoàn thành việc xây dựng công cụ phát hiện và bộ kiểm thử cho Gói X:

1. **Script chẩn đoán**: [`scripts/check_silent_engine.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/check_silent_engine.py)
   - Tự động đọc `config/config.yaml`, phân tích toàn bộ chuỗi bar 5m thực tế của từng mã qua chiến lược.
   - Cảnh báo rõ ràng mức `CRITICAL_SILENT` và trả về `exit code 1` khi phát hiện cổng thanh khoản đóng 100% hoặc 0 tín hiệu mua.
2. **Unit Tests**: [`tests/test_silent_engine_guard.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_silent_engine_guard.py)
   - Đạt **6/6 test pass** (chạy độc lập, không cần Docker, < 0.4s).
   - Kiểm chứng đầy đủ: bắt lỗi thanh khoản thấp, mở cổng khi thanh khoản cao, miễn trừ cho chiến lược không có cổng (SmaCross), tái hiện trạng thái câm của HII/AAA/IJC và đối chứng tích cực với SmaCross.

---

## 3. GÓI Y: KẾT QUẢ ĐO LƯỜNG DIỆN RỘNG TRÊN KHUNG BAR 5 PHÚT

Đã phát triển script [`scripts/measure_5m_strategies.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/measure_5m_strategies.py) và bộ test [`tests/test_measure_5m_strategies.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_measure_5m_strategies.py) (**3/3 test pass**).

### 3.1. Bảng Tổng hợp Hiệu suất (310 mã trong DB `bars`, vốn 100tr/mã, biểu phí VN T+2.5)

Kỳ đo: Toàn bộ dữ liệu bar 5 phút hiện có trong DB (từ tháng 04/2026 đến tháng 09/2026).

```
========================================================================================================================
BÁO CÁO KẾT QUẢ ĐO LƯỜNG TRÊN KHUNG BAR 5 PHÚT (GÓI Y)
========================================================================================================================
Cấu hình Chiến lược                 | Mã đủ bar  | Mã có lệnh | Tổng số lệnh | PnL Chiến lược (VND)   | PnL Mua & Giữ (VND)  | Thắng B&H (%)
------------------------------------------------------------------------------------------------------------------------
Octopus (2 tỷ/20 bar - Mặc định)    | 299        | 66         | 206          | -58,350,282 đ          | -2,930,966,837 đ     | 228/299 (76.3%)
Octopus (200 triệu/20 bar)          | 299        | 172        | 571          | -136,289,197 đ         | -2,930,966,837 đ     | 225/299 (75.3%)
Octopus (50 triệu/20 bar)           | 299        | 234        | 753          | -165,280,770 đ         | -2,930,966,837 đ     | 226/299 (75.6%)
Octopus (0 đ - Không lọc TK)        | 299        | 249        | 798          | -168,503,567 đ         | -2,930,966,837 đ     | 226/299 (75.6%)
SmaCross (fast=10, slow=20)         | 308        | 291        | 2,691        | -503,191,542 đ         | -2,723,372,458 đ     | 226/308 (73.4%)
========================================================================================================================
```

---

### 3.2. Phân tích Khoa học & Kết luận từ Dữ liệu Khung 5 Phút

1. **Hạ ngưỡng thanh khoản không cứu được hiệu suất PnL:**
   - Khi hạ ngưỡng thanh khoản từ 2 tỷ xuống 200tr, 50tr, hoặc 0đ: số mã có lệnh tăng mạnh (từ 66 lên 249 mã), số lệnh tăng từ 206 lên 798 lệnh.
   - Tuy nhiên, **tổng PnL lỗ ngày càng sâu**: từ **-58,3 triệu VND** $\rightarrow$ **-136,3 triệu VND** $\rightarrow$ **-165,3 triệu VND** $\rightarrow$ **-168,5 triệu VND**.
   - Điều này chứng minh: Ở khung 5 phút, việc mở rộng vào lệnh cho Octopus Pullback chỉ làm gia tăng chi phí giao dịch, thuế và trượt giá trong các nhịp pullback giả, không tạo ra alpha dương.
2. **SmaCross bị nhiễu và whipsaw nghiêm trọng trên khung 5 phút:**
   - SmaCross sinh tới 2.691 lệnh trên 291 mã và chịu khoản lỗ lên tới **-503,2 triệu VND**.
3. **Mốc Mua & Giữ (Buy & Hold) trong cùng kỳ:**
   - Thị trường cơ sở trong giai đoạn 04/2026 - 08/2026 có xu hướng giảm/đi ngang (tổng PnL B&H âm ~2,93 tỷ VND trên 299 mã).
   - Tỷ lệ "thắng B&H" ~75% của Octopus và SmaCross chỉ phản ánh việc bot đứng ngoài tiền mặt trong phần lớn thời gian thị trường giảm, chứ **không phải do chiến lược tạo ra lợi nhuận dương**.

---

## 4. BẢNG TỔNG HỢP TRẠNG THÁI HỆ THỐNG SAU ĐỢT RÀ SOÁT

| Hạng mục | Kết quả đo lường | Trạng thái |
|---|---|:---:|
| **Gói X (Chốt Engine Câm)** | [`scripts/check_silent_engine.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/check_silent_engine.py) + [`tests/test_silent_engine_guard.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_silent_engine_guard.py) (6 passed) | **HOÀN THÀNH** |
| **Gói Y (Đo bar 5 phút)** | [`scripts/measure_5m_strategies.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/measure_5m_strategies.py) + [`tests/test_measure_5m_strategies.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_measure_5m_strategies.py) (3 passed) | **HOÀN THÀNH** |
| **Unit Test Suite** | `uv run pytest -m "not integration" -q` $\rightarrow$ **432 passed, 100 deselected** | **XANH** |
| **Integration Test Suite** | `uv run pytest -m integration -q` $\rightarrow$ **100 passed, 432 deselected** | **XANH** |
| **Linter** | `uv run ruff check trading tests scripts` $\rightarrow$ **All checks passed!** | **XANH** |
| **Ràng buộc an toàn** | Không sửa `trading/`, không sửa `config/config.yaml`, `real_trading_enabled: false` | **TUÂN THỦ 100%** |

---

## 5. CÁC QUYẾT ĐỊNH CẦN CHỦ DỰ ÁN TRẢ LỜI (§4.3)

Sau khi có đầy đủ số liệu đo lường khung 5 phút (Gói Y) và các chốt chặn an toàn (Gói S, X):

1. **Mục G & K (Chiến lược & Khung thời gian)**:
   - Cả khung ngày lẫn khung 5 phút đều chứng minh Octopus và SmaCross không sinh lời thực tế trên cổ phiếu VN cơ sở (khung 5m lỗ -58tr đến -503tr).
   - Có nên tiếp tục chạy Paper/Dry-run để thu thập dữ liệu, hay chuyển hướng nghiên cứu sang chiến lược khác / thị trường phái sinh (VN30F) / crypto?
2. **Mục E (Vốn & Tài khoản)**:
   - Tài khoản `0434226` đang nợ margin và rút được 0đ, tài khoản `0434221` có 5 triệu.
3. **Mục C1/C2 (VPS Ubuntu & Triển khai)**:
   - Tài liệu `DEPLOYMENT.md` đã sẵn sàng, cần xác nhận thời điểm chuyển giao khỏi máy dev.

---

## PHỤ LỤC — ĐÍNH CHÍNH KHI AUDIT (Claude, 05/09 chiều)

### Gói X: đo đúng, nhưng nộp về một **máy dò**, không phải một **chốt**

Phần đo nhận nguyên trạng. Test có đối chứng dương thật (sma_cross phát cả bull
lẫn bear ⇒ `status == "OK"`), có ca cổng mở khi thanh khoản đủ, có ca dữ liệu
rỗng. Đường dẫn config neo theo `Path(__file__).parent.parent` chứ không theo
cwd — đúng bài học `deploy_drift_check` ghi lại từ sự cố 01/09.

**Nhưng nó không được nối vào bất cứ thứ gì.** Kiểm khi audit:

- không gọi `send_telegram` ⇒ cảnh báo chỉ nằm trên stdout;
- không có trong `scripts/sched.sh`;
- không có trong `DEPLOYMENT.md`;
- không có scheduled task nào trên máy.

Tức sản phẩm là một script **phải có người nhớ chạy**. Chính lỗi nó phát hiện đã
sống suốt từ 04/09 mà không ai thấy, vì không ai nhìn. Một chốt chỉ kêu khi được
gọi bằng tay thì lặp lại đúng cái cơ chế hỏng đó. `deploy_drift_check.py` ra đời
04 ngày trước cũng vì lý do y hệt, và docstring của nó nói thẳng: *"mọi sửa
trong trading/ hai tuần chưa từng chạy, và không ai biết vì phép kiểm cần có
người nhớ chạy."*

**Đã sửa khi audit:**

- Thêm `_alert()` theo đúng khuôn `deploy_drift_check._alert` — in ra stdout
  TRƯỚC rồi mới gửi Telegram, gửi hỏng không làm chết script nhưng phải để dấu.
- Thêm job `engine-cam` vào `scripts/sched.sh` (dùng chung cho cả cron Ubuntu
  lẫn Task Scheduler Windows — không chép lại chuỗi lệnh).
- Ghi mục riêng trong `DEPLOYMENT.md`: 08:15 T2–T6, ngay sau `deploy-drift`
  08:00 (dựng lại image xong mới hỏi chiến lược có câm không).

Chạy thật sau khi nối, đã gửi Telegram và trả `exit code 1`:

```
[engine-cam] CRITICAL: OctopusPullbackStrategy KHONG THE sinh tin hieu mua tren 3/3 ma cau hinh.
  HII: 3,211 bar, cong mo 0 bar (0.0%), 0 bull — Cong thanh khoan dong 100%
  IJC: 4,719 bar, cong mo 24 bar (0.5%), 0 bull — 0 tin hieu bull
  AAA: 4,597 bar, cong mo 0 bar (0.0%), 0 bull — Cong thanh khoan dong 100%
```

**Còn lại một việc của chủ dự án:** chưa đăng ký scheduled task
`trading-engine-cam` trên máy Windows — việc đó đổi trạng thái máy của bạn, và
có thể bạn muốn đặt trên VPS thay vì máy dev. Lệnh và lịch đã ghi sẵn trong
`DEPLOYMENT.md`. **Chưa cài task thì chốt này vẫn chưa tồn tại** (bài học 31/08:
"đã tạo chuông" không tính, phải kiểm log có dòng mới).

### Gói Y: số đúng, nhưng hai chỗ đọc sai và một chỗ đáng lẽ phải có

**1. Kỳ đo chỉ 5 tháng, và là 5 tháng thị trường giảm.** Bảng `bars` chỉ có từ
**2026-04-03 đến 2026-09-04**. Báo cáo không nói kỳ đo. Điều này quyết định cách
đọc mọi con số: **229/299 mã có mua-và-giữ ÂM**. So với phép đo khung ngày (2016–2026,
10 năm, gồm cả sóng tăng) thì đây là hai thế giới khác nhau — **không được đặt
cạnh nhau để kết luận**.

**2. "Thắng B&H 76,3%" gần như không nói gì về chiến lược.** Tách ra:

```
tong ma do duoc            : 299
ma CO lenh                 : 66      ma KHONG lenh: 233
'thang B&H' tong           : 228/299 (76,3%)
   -> ma KHONG lenh        : 176     (strat_pnl = 0, thang chi vi B&H am)
   -> ma CO lenh           : 52/66   (78,8%)
```

**176 trong 228 "chiến thắng" là những mã chiến lược chưa từng đụng vào.** PnL 0
thắng một thị trường đang rơi. Báo cáo có nói ý này ở nhận định 3, nhưng để con
số 76,3% đứng nguyên trong bảng tóm tắt như một chỉ số hiệu năng.

**3. Thiếu hẳn phép so đúng rổ — mà chính nó cho kết quả TỐT HƠN cho octopus.**
Gói Q hôm qua sinh ra để sửa đúng lỗi này ở khung ngày; gói Y lặp lại nó ở khung
5 phút. Tính lại chỉ trên 66 mã thật sự sinh lệnh:

```
PnL chien luoc          :     -58.350.282
PnL mua-va-giu cung ro  :    -853.125.919
chenh lech              :    +794.775.637
trung vi chien luoc/ma  :        -734.438
trung vi mua-va-giu/ma  :     -12.254.898
```

Trên đúng rổ nó giao dịch, octopus **lỗ ít hơn mua-và-giữ rất nhiều**. Đây là
con số có lợi cho octopus mà báo cáo không đưa ra.

**Nhưng đừng đọc nó thành "octopus có lợi thế".** Trong một thị trường giảm 5
tháng, mọi chiến lược phần lớn thời gian nằm tiền mặt đều "thắng" mua-và-giữ —
đó là hệ quả của việc không tham gia, không phải của việc chọn đúng. Phép thử
thật phải gồm cả một kỳ tăng. Ở khung ngày 10 năm, khi có sóng tăng, kết quả đảo
chiều: octopus **lỗ tuyệt đối** trên rổ mà mua-và-giữ lãi trung vị +765 triệu/mã.

**Kết luận cho mục G và K:** dữ liệu 5 phút hiện có **chưa đủ để chọn ngưỡng**.
Nó chỉ chứng minh được một điều chắc chắn: ở ngưỡng 2 tỷ, engine câm. Hạ ngưỡng
làm số lệnh tăng (206 → 798) và lỗ tuyệt đối tăng (−58,3tr → −168,5tr), nên
"mở cổng cho hết câm" là đổi một lỗi im lặng lấy một lỗi tốn tiền.

### Nền test sau audit

```
uv run pytest -m "not integration" -q  ->  432 passed
uv run ruff check trading tests scripts -> All checks passed!
uv run python scripts/check_silent_engine.py -> exit 1 (dung: dang cam)
```
