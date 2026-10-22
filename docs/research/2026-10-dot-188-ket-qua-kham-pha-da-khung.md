# Đợt 188: kết quả khám phá chiến lược đa khung thời gian — 0 ứng viên (audit 23/10/2026)

- Thiết kế đăng ký trước: `docs/superpowers/plans/2026-10-19-brief-dot-188-kham-pha-chien-luoc-da-khung-chong-overfit.md` (commit `0e27539`), spec H ngày 19/10.
- Agent chạy `scripts/research188_explore.py` một lần ghi nhận được, ngày 20/10 từ 06:53 đến 06:56 (giờ VN), chỉ trên `data/research188/explore/`.
- Kết quả gốc: `docs/research/dot188/` (`ideas.md`, `trial_ledger.csv`, `exploration_report.md`, `candidates.json`). `candidates.json` = `[]`, sha256 `4f53cda1…b945`.

## Phán quyết
**0 ứng viên.** Không ý tưởng nào qua đủ bốn bước. Vì không có ứng viên, bước kiểm chứng V1/V2 (§6) **không chạy**, và **không mở dữ liệu kiểm chứng nào**: mã kiểm chứng, cổ phiếu từ 2023 trở đi, crypto từ 01/09/2026 đều vẫn niêm phong. Holdout cổ phiếu 2023+ vẫn ở mức "đã mở hai lần" (đợt 175 và 177).

| Ý tưởng | Thị trường | Đỉnh EA (Sharpe/lệnh, n) | Cao nguyên | EB | Lý do loại |
|---|---|---|---|---|---|
| STK_WK_TREND_PULLBACK | CP | 0,038 (3.436) | TRƯỢT | — | láng giềng Sharpe 0,012 và 0,017 < 0,019 |
| STK_WK_VOL_BREAKOUT | CP | 0,093 (1.423) | ĐẠT | n 1.310, ròng +3,81%, p 0,010 | Calmar 0,17 < 0,86; vượt baseline (bỏ 1% đầu) −3,05% |
| STK_MN_TREND_WK_MOM | CP | −0,025 (5.325) | TRƯỢT | — | cả lưới âm |
| CRY_1D_TREND_4H_PULLBACK | Crypto | −0,139 (547) | TRƯỢT | — | cả lưới âm |
| CRY_4H_VOL_BREAKOUT | Crypto | 0,103 (926) | ĐẠT | n 827, ròng +0,00%, p 0,50 | p; Calmar 0,43; gộp 0,18% < 0,21% |
| STK_WK_DONCHIAN_CHANNEL | CP | 0,071 (1.498) | ĐẠT | n 2.014, ròng +8,25%, p 0,002 | Calmar 0,43 < 0,86; vượt baseline (bỏ 1% đầu) −3,73% |

**Đọc kết quả:**
- Ba ý tưởng cổ phiếu có lãi ròng mỗi lệnh dương trên EB (2020–2022). Nhưng đó là giai đoạn cả thị trường tăng mạnh: khi trừ lãi bình quân đều của cả universe trong cùng cửa sổ giữ lệnh, cả hai ý tưởng vào tới EB đều **thua mua-giữ đại trà**.
- Breakout crypto 4h có lãi trên EA, nhưng về **0 trên EB**. Đây là mẫu "IS đạt, ngoài mẫu tan" giống đợt 175.
- Hàng rào chặn đúng chỗ: bước cao nguyên loại 3/6 ý tưởng, cổng EB loại 3/3 ý tưởng còn lại. DSR chưa phải dùng tới.

## Audit của Claude (§8.1)
- **Test:** `uv run pytest tests/test_research188_*.py -q` cho 23 passed; ruff sạch.
- **Không truy cập DB/API:** không import `trading.storage`, không có HTTP; đường dẫn dữ liệu duy nhất là `data/research188/explore`.
- **Sổ thử khớp lưới:** 151 dòng EA = 27 × 5 + 16; có 3 dòng EB, đúng 3 ý tưởng qua cao nguyên; không trùng cấu hình. `idea_sha` không đổi giữa EA và EB. Cấu hình chọn đúng là Sharpe cao nhất trong số cấu hình có n ≥ 100.
- **Đếm độc lập trên EB:** Claude viết lại STK_WK_DONCHIAN_CHANNEL (20/12) bằng pandas, chỉ dùng chung `entry_status` và hằng phí. Kết quả **khớp tuyệt đối**: n = 2.014, lãi ròng trung bình 8,2547%.
- **Phép phá (Claude chạy lại):** (a), (c) phí, (c) funding, (d), (e), (f) chốt 400, (f) chốt sha, (h) đều làm test đỏ. **(b) và (g) vẫn XANH.** Lý do: hai test này chỉ so hằng số viết ngay trong test, không gọi code sản phẩm. Claude kiểm bằng mắt cả 6 hàm luật: mọi lệnh đều vào ở `open[t+1]` và thoát ở `open` phiên sau; cả 4 ý tưởng cổ phiếu đều có `held_sessions >= 3`. Code đúng, chỉ là chưa có test giữ.

**Lỗi và chỗ lệch tìm thấy.** Không lỗi nào đổi phán quyết, vì mọi lỗi đều làm kết quả *đẹp hơn* thực tế, không phải xấu hơn:
1. **`main()` xoá `trial_ledger.csv` mỗi lần chạy** (`unlink`). Như vậy sổ thử không còn là "chỉ ghi nối thêm", và các lần chạy thử trước (nếu có) không để lại dấu vết. Mốc thời gian file cho thấy: `ideas.md` lúc 06:40, code sửa lúc 06:52, lần chạy ghi nhận lúc 06:53. Không chứng minh được là đã có hoặc chưa có lần chạy trước. Claude đã sửa: nay sổ tồn tại thì dừng (`SystemExit`), không xoá.
2. **Equity chỉ ghi lãi khi đóng lệnh**, không định giá theo close mỗi ngày như §4.4 yêu cầu. Hệ quả là MDD bị thấp đi, Calmar bị cao lên. Các ý tưởng đã trượt Calmar kể cả với con số thổi phồng này.
3. **Lệnh còn mở ở cuối dữ liệu bị bỏ**; lệnh có nến thoát giá 0 cũng bị bỏ. Ở cấu hình Donchian, số lệnh bị bỏ vì nến thoát giá 0 là 0; tập khám phá có 3.406 dòng open = 0.
4. **Luật trong code lệch `ideas.md`:**
   - VOL_BREAKOUT có giữ tối đa 40 phiên, Donchian có giữ tối đa 50 phiên; `ideas.md` không ghi cả hai.
   - Donchian vào lệnh ở bất kỳ ngày nào khi đang không có vị thế và nến tuần đóng gần nhất là phá vỡ, chứ không phải "ngày đầu của tuần sau" như ghi.
5. **Báo cáo không có cột DSR** cho các ý tưởng bị loại trước bước 4. Validator chỉ có test cho sha sai (`return 2`) và thiếu dữ liệu (`return 3`); thiếu hai test bắt buộc là xu hướng giả phải bắt được và ngẫu nhiên phải TRƯỢT. Validator không được dùng trong đợt này.

## Hệ quả
- Đây là **phép đo âm thứ 23**: đa khung thời gian trên cổ phiếu VN (tuần/tháng lọc ngày) và crypto (1d/4h lọc 1h), sau phí thật.
- Ngân sách: chương trình 188 tiêu tốn suất giả thuyết 12–14 của tháng 10 mà không ra ứng viên.
- Nếu sau này dùng lại `research188_*`, phải sửa trước các điểm 2 và 3, và viết test thật cho (b), (g) và cho validator.
