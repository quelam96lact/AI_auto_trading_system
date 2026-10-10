# Brief đợt 182b — Hoàn thiện đường đo của 182, và vá lỗi sập ở 162

Ngày: 11/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.
Nền: commit `2a6d5eb` (hàm thuần 182, đã audit). Thiết kế đo **giữ nguyên** brief 182 v2 §1; đợt này không đổi định nghĩa nào.

## 0. Claude audit thấy gì

1. **`main()` của 182 sau cổng ngày không làm gì.** Nó in "Tiếp tục quy trình đo đạc..." rồi `return 0`.
   - Không nạp phiên, không kiểm phiên hợp lệ (§1.1), không chạy 6 cặp.
   - `load_holdout_sessions` trả `[]`.
   - Nếu để vậy, ngày 01/12 chạy ra **không có số nào**.
2. **Công cụ 162 sẽ sập ngày 01/12.** `load_all_sessions` (`scripts/screen_vn30f_orderbook.py`) không bắt lỗi file gzip bị cắt cụt. File 29/09 thật đang bị cắt cụt.
   - Claude tái hiện bằng file giả: `EOFError: Compressed file ended before the end-of-stream marker was reached`.
   - `load_holdout_sessions` của 162 cũng bị y hệt.
3. **Hai thứ thừa trong code 182:**
   - `main(..., bypass_date_gate=...)` là một đường vòng qua cổng ngày;
   - `"pytest" in sys.argv[0]` là mẹo test nằm trong code chạy thật.
4. **`calculate_event_targets` gán cứng giờ kết thúc khung VN30F.** Đợt 183 (crypto) cần truyền vào được.

## 1. Việc phải làm

### A. Vá 162 (`scripts/screen_vn30f_orderbook.py`), chỉ hai hàm
- `load_all_sessions` và `load_holdout_sessions`: bọc phần đọc **từng file** bằng `except (EOFError, OSError, zlib.error)`. `gzip.BadGzipFile` là con của `OSError`.
- File lỗi ⇒ phiên đó `is_valid=False`, có lý do "file hỏng", và in cảnh báo một dòng. **Không** dừng cả lượt chạy.
- **Không** đổi gì khác trong file. Nếu `SessionData` không có chỗ ghi lý do, chỉ in lý do ra, không thêm trường.

### B. Đường đo 182 (`scripts/screen_vn30f_orderflow.py`)

**`load_is_sessions_orderflow(data_dir)`:**
- Duyệt `<data_dir>/<hợp đồng>/<YYYY-MM-DD>.jsonl.gz`.
- Ngày ≥ `HOLDOUT_START_DATE` ⇒ bỏ qua **mà không mở file**. Ngày ngoài [`IS_START_DATE`, `IS_END_DATE`] cũng bỏ qua.
- Hai hợp đồng cùng một ngày ⇒ `ValueError`, như 162.
- Mỗi file chạy `build_footprint_bars`, lỗi đọc gzip bắt như mục A.
- **Phiên hợp lệ:** ≥ 44 trên 48 nến có giao dịch, tức ≥ 90%. Hằng 44 phải có ghi chú `ceil(0,9 × 48)`.

**`price_lookup` cho từng phiên:** `P(x)` = giá của tin khớp **cuối cùng có `trading_time ≤ x`**, kể cả tin đúng bằng x.
- Dùng danh sách `(trading_time, price)` đã lọc giống hệt `build_footprint_bars`: TRADE, B/S, khối lượng > 0, trong khung liên tục.
- Được thêm một giá trị trả về hoặc một hàm phụ, nhưng không đổi kết quả nến.

**`main()` sau cổng ngày, theo đúng thứ tự:**
1. Nạp phiên IS. In số phiên hợp lệ và không hợp lệ (kèm lý do), tổng tin U/khối lượng 0 bị loại, tổng tin ngoài khung.
2. Số phiên hợp lệ < `MIN_IS_SESSIONS` ⇒ in **"KHÔNG ĐỦ PHIÊN"**, `return 3`.
3. Kiểm đối chứng trên nến IS hợp lệ: ρ ≤ 0,3 ⇒ in **"DỮ LIỆU SIDE KHÔNG ĐÁNG TIN"**, `return 4`.
4. Tính hurdle bằng `compute_economic_hurdle(trung vị close của mọi nến IS có giá)`.
5. Với từng E ∈ {E1, E2, E3} và H ∈ {15, 30}:
   - phát hiện sự kiện trên nến của **các phiên hợp lệ**, nối theo thứ tự ngày;
   - tính mục tiêu, lọc chồng lấn, bootstrap, rồi `evaluate_pair_criteria`.
6. In bảng 6 dòng: cặp, n, n mua, n bán, trung bình y, hurdle, p, từng điều kiện, ĐẠT. `return 0`.

**Holdout, cờ `--unlock-holdout-pair E{1,2,3}_H{15,30}`:**
- Chỉ mở khi đủ ba điều kiện:
  - cặp ĐẠT trong **chính lượt chạy IS này**;
  - số file holdout **đếm theo tên file** ≥ `MIN_HOLDOUT_SESSIONS`;
  - log chưa có dòng mở holdout của đợt 182, tức chỉ mở **một** lần.
- Thiếu điều kiện nào ⇒ in lý do, `return 5`, **không** ghi log, **không** mở file holdout.
- Đủ điều kiện:
  1. **ghi** một dòng có cả "đợt 182" và tên cặp vào `docs/holdout-unlock-log.md`;
  2. sau đó mới nạp phiên ≥ 2026-12-01;
  3. đo **riêng cặp đó** với hurdle của IS;
  4. in kết quả.
- `verify_holdout_log_unlocked` phải đòi dòng có **cả** "đợt 182" **và** tên cặp.

**Dọn:** xoá tham số `bypass_date_gate` và mẹo `sys.argv[0]`. Test gọi `main(args=[...], today=...)`.

### C. `calculate_event_targets(..., block_end_fn=None)`
- Mặc định là giờ kết thúc khung VN30F hiện nay; hành vi cũ không đổi.
- Đợt 183 sẽ truyền hàm riêng.

## 2. Test (dữ liệu tổng hợp trong `tmp_path`, không đụng `data/orderbook/`)

12. **Đầu-cuối**, với `today = 2026-12-01`, `--data-dir` là thư mục tạm. Dữ liệu dựng bằng code:
    - 41 phiên IS hợp lệ;
    - 1 file IS bị cắt cụt;
    - 1 phiên IS chỉ có 10 nến có giao dịch;
    - 1 file ngày 2026-12-02.

    Assert:
    - `return 0`;
    - output báo 41 hợp lệ, cắt cụt là không hợp lệ với lý do "file hỏng", phiên thưa là không hợp lệ;
    - có bảng 6 dòng;
    - **file 2026-12-02 không bị mở**: theo dõi các đường dẫn truyền vào `iter_file_messages` (spy/monkeypatch).
13. Cùng kiểu nhưng chỉ 39 phiên hợp lệ ⇒ có "KHÔNG ĐỦ PHIÊN" và `return 3`.
14. Phiên tổng hợp mà `side` gán ngẫu nhiên, độc lập với hướng giá ⇒ `return 4`.
15. `price_lookup`: tin đúng lúc x được lấy; tin lúc x + 1 giây thì không; tin `U` đúng lúc x bị bỏ qua.
16. **Holdout:**
    - cặp không ĐẠT ⇒ `return 5`, log tạm không đổi, loader holdout (mock) không được gọi;
    - cặp ĐẠT (dùng monkeypatch kết quả IS) ⇒ trình tự gọi là **ghi log rồi mới nạp holdout** (kiểm bằng một danh sách ghi thứ tự);
    - lần hai cùng cặp ⇒ `return 5`.
17. **162 với file cắt cụt:**
    - `load_all_sessions` trên thư mục tạm có một file bị cắt **không sập**, và phiên đó `is_valid=False`;
    - một file lành cùng thư mục vẫn được đọc.
18. `calculate_event_targets` với `block_end_fn` riêng: sự kiện có `t_end + H` bằng đúng giờ kết thúc ⇒ giữ; vượt 1 phút ⇒ bỏ.

**Bốn phép phá bắt buộc**, cùng quy tắc sao lưu/khôi phục như brief 182:

| Phép phá | Test phải đỏ |
|---|---|
| (vii) bỏ dòng loại ngày ≥ 2026-12-01 trong loader IS của 182 | 12 |
| (viii) coi mọi phiên là hợp lệ | 12 hoặc 13 |
| (ix) nạp holdout trước khi ghi log | 16 |
| (x) bỏ `except` ở `load_all_sessions` của 162 | 17 |

**Không thêm cờ phá hoại vào code chạy thật nữa.** Phép phá làm bằng cách sửa bản sao file rồi khôi phục.

## 3. Cổng kiểm cuối
- **GitNexus** (chỉ `gitnexus ... -r AI_auto_trading_system` hoặc `node .gitnexus/run.cjs ...`, không `npx`):
  - `impact` upstream cho `load_all_sessions`, `load_holdout_sessions` (162), `calculate_event_targets` và `main` (182) **trước khi sửa**. Báo mức rủi ro;
  - `detect-changes --scope all` sau khi sửa.
- `uv run pytest -m "not integration" -q` trước và sau: dán hai con số. Test cũ của 162 (`tests/test_screen_vn30f_orderbook.py`, nếu có) phải xanh nguyên.
- `uv run ruff check trading tests scripts` sạch.
- `uv run python scripts/screen_vn30f_orderflow.py` hôm nay vẫn in thông báo cổng ngày và trả 2. Dán output.

## 4. Bất biến
- **Chỉ sửa:** `scripts/screen_vn30f_orderflow.py`, `tests/test_screen_vn30f_orderflow.py`, và **đúng hai hàm** nêu ở mục A trong `scripts/screen_vn30f_orderbook.py` cùng test của nó.
- **Không mở, liệt kê hay đếm** `data/orderbook/` thật. **Không** ghi `docs/holdout-unlock-log.md` thật.
- **Không:** commit, push, ghi DB, gọi SSI, chạy `scripts/sched.sh` hay máy ghi.

## 5. Báo cáo cho Claude
- pytest trước/sau, ruff, output cổng ngày.
- Bảng bốn phép phá, kết quả `impact` và `detect-changes`.
- Mục "brief mơ hồ ở đâu".
- Câu chốt: *"Tôi không mở file nào trong data/orderbook/."*
