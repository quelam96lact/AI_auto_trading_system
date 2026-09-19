# Brief đợt 64 — Kiểm định theo từng năm, chống overfit cho buy-and-hold có nhịp

Ngày giao: 19/09/2026 (thứ Bảy, khuya).
Base: main hiện tại (đợt 62 đã merge tại `e1f786b`).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Bối cảnh — đọc trước

Đợt 62 (đã merge, đáng tin) đo được, sau khi sửa đòn vay ảo:

| Kỳ | PnL có nhịp | PnL B&H thuần | Chênh lệch |
|---|---|---|---|
| Trong mẫu 2016-2022 | +1.407,49 tỷ | +1.007,12 tỷ | **+400,37 tỷ** (thắng) |
| Ngoài mẫu 2023-2026 | +312,72 tỷ | +657,94 tỷ | **-345,22 tỷ** (thua) |

Câu hỏi chưa trả lời: khoản thắng +400,37 tỷ trong mẫu có phải một lợi thế bền vững, hay chỉ đến
từ 1-2 năm bất thường (2018 giảm sâu, 2020 Covid, 2022 downtrend) — nếu vậy, việc chọn đúng
2016-2022 làm "trong mẫu" đã vô tình là một dạng may rủi, dù ngưỡng breadth 0,40/0,60 đã đóng băng
từ đợt 9 và không hề được tinh chỉnh theo dữ liệu.

## 1. Vì sao KHÔNG làm walk-forward kinh điển (train → refit → test lặp lại)

Walk-forward cổ điển tồn tại để phát hiện overfit THAM SỐ: tối ưu tham số trên một cửa sổ "train",
kiểm trên cửa sổ "test" liền sau, lặp lại trên nhiều cửa sổ trượt. Nhưng chiến lược này **không có
bước tối ưu nào để lặp lại** — ngưỡng breadth 0,40/0,60 đã đóng băng trước khi kiểm định (đợt 9),
không hề được tinh chỉnh lại trên bất kỳ giai đoạn con nào. Dựng một khung "train/refit/test" ở
đây sẽ ngụy tạo một bước tối ưu không tồn tại.

Việc thực sự cần, và đúng câu hỏi đang hỏi ("có overfit không"): đo hiệu suất của **cùng một quy
tắc cố định, không đổi** trên **nhiều giai đoạn con độc lập**, xem lợi thế +400,37 tỷ có xuất hiện
đều qua nhiều năm hay dồn vào một vài năm bất thường. Đây là kiểm định **ổn định theo giai đoạn
con** (sub-period stability), không phải walk-forward theo nghĩa tối-ưu-rồi-kiểm. Nếu bạn (agent)
thấy cách hiểu khác hợp lý hơn, dừng lại và hỏi lại Claude trước khi code — đừng tự chọn một cách
đọc rồi lặng lẽ triển khai.

## 2. Ràng buộc

Không đổi ngưỡng breadth 0,40/0,60. Không đụng `trading/`. Không sửa `config/config.yaml`. Không
commit, không push.

---

## Task 1 — Thêm `--task by-year` vào `scripts/measure_regime_hold.py`

### 1.1. Không đổi các hàm đã kiểm chứng

**Không sửa** `simulate_symbol_regime_hold`, `run_regime_hold_benchmark`, `compute_max_drawdown`,
`count_regime_switches` — dùng nguyên vẹn, gọi lại y hệt cách `--task all` đang gọi. Chỉ thêm
nhánh mới trong `main()`.

### 1.2. Quy tắc chia năm — đóng băng, không tự diễn giải thêm

Lặp qua từng năm dương lịch từ **2016 đến 2026**:
- 2016 → 2025: trọn năm, `[YYYY-01-01, YYYY-12-31 23:59:59]` (giờ `TZ` như code hiện có).
- 2026: cắt tại **28/08/2026** để khớp đúng ranh giới `out_to` đã dùng ở nhánh `--task out-sample`
  hiện có trong file — **không tự chọn mốc khác** (ví dụ không dùng 31/12/2026 vì dữ liệu chưa
  chắc có tới đó, phải khớp đúng biên đã kiểm chứng ở đợt 61/62).

Với mỗi năm, gọi:
```python
run_regime_hold_benchmark(storage, symbols, frm, to, prior_regime_by_date, args.capital)
```
**Vốn RESET về `args.capital` mỗi năm** — không dồn lãi/lỗ năm trước sang năm sau, mỗi năm là một
phép đo độc lập (khác đường vốn liên tục của `--task all`). Vì vậy **tổng PnL cộng dồn qua 11 năm
sẽ KHÔNG khớp con số của `--task all`** — đây là chủ ý, phải nói rõ trong báo cáo, **không được
cố điều chỉnh cho khớp**.

### 1.3. Định dạng in ra

Một bảng duy nhất, mỗi dòng một năm, các cột:

```
Năm | %ngày HOLD | Số lần đổi trạng thái | PnL có nhịp (tỷ) | PnL B&H thuần (tỷ) | Chênh lệch (tỷ) | MDD có nhịp | MDD B&H | skipped_buys
```

Dòng cuối bảng: đếm "thắng B&H X/11 năm, thua Y/11 năm" (thuần đếm, không bình luận thêm).

---

## Task 2 — Kiểm chứng (bắt buộc dù không đổi hàm cũ, vì logic chia-năm là mới)

### 2.1. Test mới — chứng minh ranh giới năm đúng, không rò rỉ, không lệch

Thêm test (trong `tests/test_regime_hold.py` hoặc file mới `tests/test_regime_hold_by_year.py` —
tự quyết cấu trúc, miễn giữ đúng style hiện có của repo):

1. Dựng bars giả trải dài đúng 2 năm dương lịch liên tiếp (ví dụ vài phiên rải trong 2023, vài
   phiên rải trong 2024, có ít nhất một phiên sát ranh giới 31/12 và 01/01).
2. Chạy nhánh/hàm chia-theo-năm của bạn cho 2 năm này.
3. **Độc lập**, tự gọi `run_regime_hold_benchmark` hai lần thủ công với đúng ranh giới
   `[2023-01-01, 2023-12-31 23:59:59]` và `[2024-01-01, 2024-12-31 23:59:59]`.
4. Khẳng định kết quả hai cách **giống hệt nhau** (từng trường: `strat_pnl`, `bh_pnl`, `strat_mdd`,
   `bh_mdd`, `total_buy_trades`, `total_sell_trades`) — chứng minh việc chia mốc năm không lệch
   ranh giới, không off-by-one, không rò rỉ bar của năm này sang năm kia.

### 2.2. Chứng minh test phân biệt được

Tạm chỉnh sai 1 ngày ở ranh giới cắt năm trong code của bạn (ví dụ dùng `2023-12-30` thay vì
`2023-12-31` làm mốc cuối năm 2023), chạy lại test ở 2.1, xác nhận **ĐỎ** (vì giờ ranh giới hai
cách tính lệch nhau khi có bar rơi đúng ngày 31/12). Khôi phục lại, xác nhận **XANH**, dán cả hai
lần chạy vào báo cáo.

### 2.3. Chạy đo thật

```bash
uv run python scripts/measure_regime_hold.py --task by-year --exclude-file exclusions.txt
```

Dán nguyên văn bảng đầy đủ 11 năm (2016-2026) vào báo cáo.

### 2.4. Hồi quy

- `uv run pytest -m "not integration" -q` — không test cũ nào đổi từ pass sang fail; báo rõ tổng
  số test mới (từ 699 lên bao nhiêu).
- `uv run ruff check trading tests scripts` sạch.

---

## 3. Không làm

- **Không đổi ngưỡng breadth 0,40/0,60**, không đổi quy tắc HOLD/CASH.
- **Không tối ưu/tinh chỉnh bất kỳ tham số nào dựa trên số liệu by-year vừa đo được** — nhìn số
  rồi chỉnh ngược lại tham số chính là overfit thêm một lớp nữa (data snooping). Nếu thấy cám dỗ
  làm vậy khi thấy số liệu (ví dụ "chỉ cần đổi ngưỡng thành X là ngoài mẫu cũng thắng"), **DỪNG
  LẠI, báo cáo cho Claude, không tự sửa.**
- **Không tính lại hay sửa `--task all`/`--task in-sample`/`--task out-sample`** — giữ nguyên như
  đợt 62.
- Không commit, không push.

---

## 4. Báo cáo cho Claude

1. Bảng đầy đủ 11 năm (mục 2.3).
2. `git diff scripts/measure_regime_hold.py` — xác nhận chỉ `main()` đổi, 4 hàm còn lại của file
   không đổi một dòng.
3. `git diff`/nội dung file test mới hoặc sửa.
4. Bằng chứng test phân biệt được (mục 2.2), dán nguyên văn cả hai lần chạy (đỏ và xanh).
5. Kết quả `pytest`/`ruff` (mục 2.4).
6. Nhận xét — **chỉ mô tả, không kết luận**: bao nhiêu năm thắng/thua B&H, năm nào chênh lệch lớn
   nhất theo hướng nào. Việc kết luận "có nên triển khai không" là của Claude/chủ dự án sau khi
   audit, không phải việc của brief này.
