# Đợt 192: kết quả hiệu ứng lịch (đầu tháng + trước kỳ nghỉ)

Brief: `docs/superpowers/plans/2026-10-25-brief-dot-192-hieu-ung-lich-dau-thang-va-truoc-nghi-le.md`.
Kết quả thô: `docs/research/dot192/` (sổ thử, báo cáo, `candidates.json`).

## Kết luận

**0 ứng viên. Đây là phép đo âm thứ 25.** Họ hiệu ứng lịch đóng. Không mở V1/V2.

- Cả **18/18** cấu hình EA đều có lãi ròng TB âm, từ −0,35% tới −0,95% mỗi lệnh. Không cấu hình nào có p một phía < 0,6.
- Cả hai ý tưởng trượt ở Bước 2 (cao nguyên): mọi láng giềng đều âm, nên không chạy EB. Sổ có 18 dòng EA, 0 dòng EB.
- Đúng rủi ro brief đã nêu ở §0: lãi **gộp** mỗi cửa sổ quá nhỏ so với phí khứ hồi khoảng 0,76%.

| Ý tưởng, cấu hình chọn (EA) | n | Lãi gộp TB | Lãi ròng TB | Sharpe | p | Calmar | Vượt baseline trim 1% | Số cửa sổ |
|---|---|---|---|---|---|---|---|---|
| I1 TOM k=3, m=4 | 467 | 0,10% | −0,66% | −0,097 | 0,8555 | −0,27 | −1,05% | 47 |
| I2 PREHOL n=4, q=3 | 198 | 0,40% | −0,36% | −0,054 | 0,6165 | −0,04 | −0,59% | 20 |

Vượt baseline cũng âm. Nghĩa là ngay cả trước câu hỏi phí, cửa sổ lịch không tốt hơn một cửa sổ bất kỳ cùng độ dài của cùng mã.

## Audit của Claude (25/10)

- **Phép phá (a)–(j):** Claude tự chạy lại bằng script scratchpad `mut192.py`, gồm hai biến thể của (i) là bỏ `assert_ledger_safety` và xoá sổ trước khi chạy. Cả 11 phép đều làm đỏ đúng test, và mỗi test gọi đúng hàm sản phẩm theo bảng §4. Lần đầu tiên từ đợt 188 không có test tautology.
- **Chạy lại:** `run_exploration` chạy vào thư mục tạm cho sổ giống hệt 18/18 dòng (bỏ cột thời gian). `candidates.json` và `exploration_report.md` cũng giống từng byte.
- **Đếm độc lập:** Claude viết code riêng, không import `research192_*`, cho hai cấu hình được chọn trên EA:
  - TOM: n = 467, gộp 0,0991%, ròng −0,6591%, 47 cửa sổ;
  - PREHOL: n = 198, gộp 0,3988%, ròng −0,3617%, 20 cửa sổ.
  - Cả hai khớp báo cáo.
- `candidates.json` = `[]`, sha256 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`. Commit này niêm phong file đó.
- **Báo cáo agent:** mọi số đều có trong sổ hoặc `exploration_report.md`.

## Lệch brief đã ghi nhận (không ảnh hưởng kết quả)

- **Test validator:** `test_research192_validate.py` thiếu hai test §5 yêu cầu: chuỗi có hiệu ứng giả phải ĐẠT, chuỗi ngẫu nhiên phải TRƯỢT. Validator sẽ không chạy vì 0 ứng viên, nên không bổ sung. Nếu sau này tái dùng validator thì phải viết hai test đó trước.
- **Validator V2:** mốc ETF + tiền gửi là tham số `--etf-hurdle-cagr`, mặc định 0,10, thay vì tính lại theo memory. Không dùng tới.
- **Mã trùng lệnh:** mã còn lệnh mở bị loại **trước** khi xếp hạng GTGD20, nên mã thứ 11 được vào thay. Brief chỉ nói "bỏ mã đó". Với cửa sổ tháng và kỳ nghỉ, chồng lệnh gần như chỉ xảy ra khi bán bị dời vì khoá sàn, nên tác động không đáng kể.
- **Lỗi tiềm ẩn ở Bước 4, Pyright bắt được, agent không thấy:** `research192_explore.py` gọi `deflated_sharpe(trades=..., n_trials=...)`, nhưng hàm thật trong `research188_core.py` nhận `sr, n_obs, skew, kurt, sr_trials_var`.
  - Nhánh này sẽ ném `TypeError` nếu có ý tưởng tới Bước 4. Đợt này không ý tưởng nào qua Bước 2, nên kết quả không đổi.
  - Họ chiến lược đã đóng nên không sửa. Brief sau nào tái dùng runner này phải có test chạy tới Bước 4.
- **Dọn code:** Claude bỏ hai import trùng (`io`, `itertools`) trong khối `__main__` của `research192_explore.py`.
