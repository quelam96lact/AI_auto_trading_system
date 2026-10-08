# Brief đợt 165 — Mốc chuẩn "w% ETF VN30 + phần còn lại gửi tiết kiệm", đo đủ chi phí (ĐĂNG KÝ TRƯỚC)

Ngày: 08/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Khung đánh giá: `docs/superpowers/specs/2026-10-04-muc-tieu-va-nguong-danh-gia-chien-luoc.md` (vốn rủi ro 100 triệu, MDD ≤ 7%, MDD backtest ≤ 4,7%, hurdle 9%/năm).
Đây là **giả thuyết 2/3 của tháng 10/2026** (spec mục F). Chủ dự án chọn hướng này ngày 08/10/2026.

---

## 0. Câu hỏi, và vì sao đây là mốc chuẩn chứ không phải chiến lược

**Câu hỏi:** một danh mục không cần chiến lược nào, gồm `w` phần vốn mua-và-giữ ETF `E1VFVN30` và `1 − w` gửi tiết kiệm, tái cân bằng mỗi năm một lần, cho lãi bao nhiêu và MDD bao nhiêu sau đủ phí, thuế và trượt giá?

**Vì sao cần:** spec §1 suy ra vị thế ETF khoảng 15% vốn thì giữ được MDD 7%. Ước tính thô: 0,15 × 13,34% + 0,85 × 9% ≈ 9,6%/năm, MDD ≈ 7,2%, tức phương án "không làm gì" đã sát cả hurdle lẫn trần MDD. **Mọi chiến lược về sau phải thắng con số đo được ở đây**, không chỉ thắng tiền gửi. Phép đo này biến ước tính thô thành số đo có chi phí thật.

**Kỳ vọng trước của Claude (ghi để đối chiếu, không phải đáp án):**
- MDD chủ yếu đến từ phần ETF nên tỷ lệ gần tuyến tính theo `w`: `w = 15%` sẽ **trượt** mốc backtest 4,7% (≈ 7%), còn `w = 10%` nằm sát biên 4,7%.
- Lãi gần như do giả định lãi suất tiền gửi quyết định. Với `r = 9%`, mọi `w` nhỏ đều "thắng" 9% gần như theo định nghĩa. Vì vậy bảng độ nhạy theo `r` mới là phần thông tin chính.

**Không hỏi:** nên phân bổ bao nhiêu. Lưới `w` chỉ để báo cáo; **không chọn `w` tốt nhất trên dữ liệu này.**

## 1. Thiết kế đăng ký trước — KHÔNG đổi sau khi thấy số

### 1.1 Dữ liệu và niêm phong
- Mã `E1VFVN30`, bảng `bars_daily`, đọc bằng `storage.read_daily_bars` + `clean_bars` (`trading/stock_study.py`), bỏ phiên giá ≤ 0, giống đợt 161.
- **Niêm phong:** dữ liệu cổ phiếu/ETF từ **01/01/2023** là tập niêm phong của repo (`SEALED_START`, đợt 120). Ghi chú: `docs/holdout-unlock-log.md` dòng 04/10 đã ghi E1VFVN30 từ 2023 không còn ngoài mẫu cho họ volatility targeting; phân bổ tĩnh là họ khác, nên vẫn giữ kỷ luật niêm phong.
- **IS:** phiên đầu tiên của 2017 tới 30/12/2022. Hàm đọc IS phải gọi `validate_sealed_bars` (nến ≥ 01/01/2023 thì ném lỗi).
- **Tập niêm phong:** 2023-01-03 → 30/09/2026. **Agent không chạy phần này.** Script có hàm riêng, chỉ chạy với cờ tường minh, ghi một dòng vào `docs/holdout-unlock-log.md` **trước** khi đọc. Claude chạy đúng một lần sau khi audit IS, chỉ cho các cấu hình ở §1.6.

### 1.2 Danh mục
- Lưới `w` ∈ {5%, 10%, 15%, 20%, 25%, 30%}. **Biến thể chính: `w = 15%`** (chốt trước, lấy từ spec §1).
- Vốn đầu 1,0. Ngày đầu: mua ETF `w` ở giá OPEN phiên đầu, phần còn lại vào tiền gửi.
- **Tái cân bằng (chính):** mỗi năm một lần. Quyết định ở CLOSE phiên cuối năm, khớp ở OPEN phiên đầu năm sau, đưa tỷ trọng ETF về đúng `w` (tính trên tổng tài sản ròng lúc khớp). **Biến thể phụ:** không tái cân bằng.
- Tiền chuyển giữa ETF và tiền gửi đi ngay, không phạt rút trước hạn. Đây là giả định có lợi cho mốc chuẩn; ghi rõ trong báo cáo.

### 1.3 Chi phí
- Chỉ phần ETF chịu phí. Mua: `FEE_RATE + truot_gia`; bán: `FEE_RATE + SELL_TAX_RATE + truot_gia`, với `truot_gia = SLIPPAGE_BPS / 10_000`. **Import từ `trading/paper_broker.py`**, không gõ lại số (FEE_RATE hiện là 0,28%).
- Không phí/thuế cho tiền gửi. Thuế lãi tiền gửi: không trừ (giả định, ghi trong báo cáo; chưa kiểm nguồn).
- Cuối kỳ: ghi nhận giá trị ETF **sau khi trừ phí bán giả định** (như `buy_hold` đợt 161), để so được với tiền mặt.

### 1.4 Lãi tiền gửi
- Lãi suất năm cố định `r`, tính lãi kép theo **ngày lịch** giữa hai phiên liên tiếp: hệ số `(1 + r) ** (số_ngày_lịch / 365)`. Ví dụ thứ Sáu → thứ Hai là 3 ngày.
- **Chính: `r = 9%`** (spec, hurdle 3; chủ dự án cung cấp, **chưa đối chiếu lãi suất ngân hàng lịch sử 2017–2026**). **Độ nhạy:** `r` ∈ {0%, 5%, 7%, 9%}. Mức 0% cho thấy riêng phần ETF đóng góp gì. Không thêm mức nào khác, không tự tra lãi suất lịch sử.

### 1.5 Chỉ số (mỗi tổ hợp `w` × `r` × kiểu tái cân bằng)
- CAGR theo ngày lịch (giống `cagr` của đợt 161; import nếu dùng được).
- **Phần vượt tiền gửi** = CAGR − r.
- MDD trên **tổng tài sản** (`trading/metrics.max_drawdown`), không phải riêng phần ETF.
- MDD tệ nhất trong một năm dương lịch, và lợi nhuận năm tệ nhất.
- Số giao dịch ETF, tổng phí trên vốn đầu.
- Ba cột ĐẠT/KHÔNG ĐẠT đối chiếu spec, **chỉ mô tả, không dùng để chọn**: (a) MDD ≤ 4,7%; (b) MDD ≤ 7%; (c) CAGR ≥ 9%.

### 1.6 Phần niêm phong Claude sẽ chạy (đã chốt, không mở thêm)
Chỉ hai cấu hình: `w = 15%`, tái cân bằng năm, `r = 9%` và `r = 0%`. Cùng chỉ số §1.5 trên 2023-01-03 → 30/09/2026.

### 1.7 Kỷ luật chạy
Agent chạy phép đo IS thật **đúng một lần**. Lỗi code buộc chạy lại thì báo cả hai lần và nói lỗi gì. Cấm thêm `w`, `r`, kiểu tái cân bằng, hay đổi giờ khớp lệnh.

## 2. Phạm vi
- **Được thêm:** `scripts/measure_etf_deposit_mix.py`, `tests/test_measure_etf_deposit_mix.py`, báo cáo `docs/superpowers/research/2026-10-08-dot-165-moc-chuan-etf-cong-tien-gui.md`.
- **Được import, không sửa:** `scripts/measure_vol_target_etf.py`, `trading/stock_study.py`, `trading/metrics.py`, `trading/paper_broker.py`, `trading/calendar_vn.py`.
- **Không sửa:** mọi file khác. **Không ghi DB** (chỉ đọc). Cấm chạy `scripts/sched.sh`. Thấy vấn đề ngoài phạm vi → báo cáo, không tự sửa.
- GitNexus: `context` cho các hàm dùng lại trước khi viết, `detect_changes` sau khi xong.

## 3. Kiểm chứng — TDD, test trước, thấy đỏ rồi mới viết code
Test trên nến dựng tay, không đọc DB.
1. **`w = 0`:** tài sản đúng bằng lãi kép tiền gửi tính tay, sai số < 1e-12.
2. **`w = 1`, không tái cân bằng:** đường tài sản trùng `buy_hold` của `scripts/measure_vol_target_etf.py` trên cùng nến, sai số < 1e-12.
3. **Lãi theo ngày lịch:** hai phiên thứ Sáu → thứ Hai cộng đúng 3 ngày lãi.
4. **Tái cân bằng năm:** chỉ khớp ở OPEN phiên đầu năm; giữa năm không có giao dịch; sau khớp, tỷ trọng ETF bằng `w` tại giá OPEN.
5. **Chi phí:** giá ETF đứng yên qua một lần tái cân bằng → tài sản giảm đúng `|notional| × đơn giá phía` tính tay; phần tiền gửi không chịu phí.
6. **MDD trên tổng tài sản:** dựng chuỗi ETF giảm 50% với `w = 10%`, `r = 0` → MDD ≈ 5%, không phải 50%.
7. **Niêm phong:** hàm IS ném lỗi khi có nến ≥ 01/01/2023. Hàm niêm phong không có cờ thì từ chối; có cờ thì ghi log (đường dẫn `tmp_path` trong test) **trước** khi đọc. Dùng giả lập để kiểm thứ tự gọi.
8. **Không dùng tương lai:** đổi giá mọi phiên sau ngày `d` thì tài sản tại các phiên ≤ `d` không đổi.

Kiểm thử phá hoại: sao lưu file ra ngoài repo; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Tính lãi theo số phiên thay vì ngày lịch → test 3 đỏ.
- Khớp tái cân bằng ở CLOSE thay vì OPEN → test 4 hoặc 8 đỏ.
- Bỏ `validate_sealed_bars` ở hàm IS → test 7 đỏ.
- Tính phí cho cả phần tiền gửi → test 5 đỏ.
- Tính MDD trên riêng phần ETF → test 6 đỏ.

```
uv run pytest tests/test_measure_etf_deposit_mix.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

## 4. Hoàn thành khi
- 8 test xanh, năm bước phá hoại mỗi bước làm đỏ đúng test đã nêu.
- Bộ đầy đủ không có test mới đỏ. Mốc 08/10: `1761 passed, 150 deselected`; dán số trước và sau.
- ruff sạch; `detect_changes` chỉ gồm ba file mới.
- Đã chạy phép đo IS thật **một lần** (chỉ đọc DB) và báo cáo có đủ:
  - số phiên, ngày đầu/cuối IS, số phiên bị bỏ vì giá ≤ 0;
  - bảng chính: `w` × kiểu tái cân bằng, với `r = 9%`;
  - bảng độ nhạy: `w` × `r`, tái cân bằng năm;
  - bảng theo năm của biến thể chính;
  - đối chiếu kỳ vọng trước của Claude ở §0, ghi đúng/sai, không bình luận thêm;
  - mục "Giả định có lợi cho mốc chuẩn" (rút tiền không phạt, không thuế lãi, `r` cố định chưa kiểm nguồn).

## 5. Báo cáo cho Claude
1. Output pytest/ruff và bảng năm bước phá hoại.
2. `detect_changes`.
3. Lệnh đã dùng để chạy IS và output đầy đủ (dán nguyên văn).
4. Một câu xác nhận: "Tôi không chạy phần niêm phong và không ghi vào `docs/holdout-unlock-log.md`."
5. Mọi chỗ brief mơ hồ mà agent phải tự diễn giải; không im lặng chọn.

## 6. Việc Claude làm sau khi duyệt
- Tự tính lại độc lập ít nhất một ô (biến thể chính, `r = 9%`).
- Chạy phần niêm phong đúng một lần cho hai cấu hình ở §1.6, ghi log.
- Ghi kết quả vào spec như mốc chuẩn tham chiếu, commit, push.
