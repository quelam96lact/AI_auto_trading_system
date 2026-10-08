# Brief đợt 166 — Rút ngắn bộ test mà không làm test yếu đi

Ngày: 08/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.

## 0. Vì sao, và vì sao KHÔNG tối ưu chỗ khác

Chủ dự án yêu cầu "tối ưu hệ thống". Claude đo trước khi giao (08/10, 23:00):

| Chỗ | Số đo | Kết luận |
|---|---|---|
| Container | collector 52 MB, engine 36 MB, Postgres 328 MB / 1 GB, CPU < 3% | Không có gì để tối ưu |
| DB | 821 MB, bảng lớn nhất `binance_klines` 128 MB | Không có gì để tối ưu |
| **Bộ test đầy đủ** | **1919 test, 390 giây** (lần chạy chiều cùng ngày: 175 giây) | **Đây là chỗ chậm thật** |

Bộ test quan trọng vì hook pre-push chạy **toàn bộ** nó trước mỗi lần push. Lệnh đo: `uv run pytest -q --durations=25 -p no:cacheprovider`. Năm test chậm nhất:

| Test | Giây | Nghi vấn của Claude (CHƯA kiểm, agent phải đo) |
|---|---|---|
| `test_screen_vn30f_orderbook.py::test_main_niem_phong_du_dieu_kien_ghi_log_truoc_doc_holdout_sau` | 35,3 | `_evaluate_holdout_pair` gọi `run_block_permutation_test(n_permutations=1000)` **gắn cứng**, nên cờ `--permutations 10` của test không tới được nhánh niêm phong |
| `test_garch_vol.py::test_forecast_recovers_volatility_level` | 20,6 | fit GARCH trên chuỗi dài |
| `test_alert_outbox.py::test_qua_200_tin_bo_tin_cu_nhat_va_lan_gui_ke_tiep_co_dong_da_bo` | 20,1 | 203 lần `enqueue`, mỗi lần ghi lại cả file |
| `test_engine_main.py::test_real_crossover_nav_reread_recovery_warns_once` | 14,4 | chưa rõ |
| `test_scripts_convention.py::test_moi_script_khong_dau_cham_thuoc_mot_trong_ba_nhom` | 14,1 | dựng regex cho từng tên script rồi quét mọi file test |

Kèm theo: `test_engine_main.py::test_real_crossover_nav_reread_stays_broken_silent` 9,5 giây, `test_scripts_convention.py::test_khai_bao_khong_lo_thoi_va_khong_tro_vao_file_khong_ton_tai` 7,7 giây.

**Nguyên tắc số một: test nhanh hơn mà bắt lỗi kém đi là thất bại, không phải thành công.** Mọi test được sửa phải chứng minh vẫn đỏ với đúng lỗi nó canh (§3).

## 1. Việc làm, theo thứ tự

1. **Đo nguyên nhân trước, chưa sửa gì.** Với 7 test ở §0, chạy riêng từng test với `--durations=0`, và nếu cần thì `python -m cProfile -s cumtime -m pytest <test>`.
   - Báo cho từng test: thời gian, và 3 hàm tốn nhiều nhất kèm số giây.
   - Nghi vấn của Claude ở §0 có thể sai; báo đúng/sai cho từng cái.
   → **kiểm chứng bằng:** bảng 7 dòng trong báo cáo, mỗi dòng có số đo thật.
2. **Sửa từng test**, ưu tiên theo số giây tiết kiệm được. Chọn cách ít xâm lấn nhất:
   - Giảm kích thước dữ liệu hoặc số vòng **chỉ khi** test vẫn kiểm đúng điều nó tuyên bố (ví dụ test thứ tự "ghi log trước, đọc sau" không cần 1000 hoán vị thật, nên được giả lập phần đánh giá).
   - Đọc file hoặc dựng regex **một lần** thay vì lặp lại.
   - Giả lập phần tính toán nặng không phải đối tượng của test.
   → **kiểm chứng bằng:** test xanh, số giây mới, và bước phá hoại ở §3.
3. **Đo lại cả bộ** bằng đúng lệnh ở §0, hai lần liên tiếp (máy laptop dao động mạnh: 175 so với 390 giây).
   → **kiểm chứng bằng:** dán dòng tổng và bảng `--durations=25` của cả hai lần.

## 2. Phạm vi
- **Được sửa:** chỉ các file test chứa 7 test ở §0. Được thêm fixture hoặc hàm trợ giúp trong chính các file đó.
- **Không được sửa code sản phẩm** (`trading/`, `scripts/`). Nếu một test chỉ nhanh được khi sửa code sản phẩm, ví dụ `_evaluate_holdout_pair` cần tham số số hoán vị, thì **dừng ở test đó và báo**: đề xuất sửa gì, tiết kiệm bao nhiêu giây, rủi ro gì.
  - Lưu ý riêng: số 1000 hoán vị ở nhánh niêm phong là thiết kế đăng ký trước của đợt 162. Không được đề xuất cho người dùng CLI hạ con số này.
- **Không được:** xóa test, đánh dấu `skip`/`slow`, gộp hai test thành một, hạ ngưỡng `assert`, đổi seed để test "may mắn" qua, thêm dependency (kể cả `pytest-xdist`), đổi `pyproject.toml` hay hook pre-push.
- Không đụng test khác ngoài 7 test (kể cả khi thấy nó chậm); muốn thì báo.
- GitNexus: chỉ mục đang cũ, chạy `npx gitnexus analyze` trước. Chạy `detect_changes` sau khi xong.

## 3. Bằng chứng test không yếu đi (bắt buộc cho mỗi test được sửa)
Với mỗi test được sửa, làm **một bước phá hoại vào code sản phẩm** đúng điều test đó canh, chạy bản test **mới**, và test phải đỏ. Sao lưu file ra ngoài repo trước khi phá; cấm `git checkout/restore/stash`. Khôi phục xong thì chạy lại cho xanh.

Bước phá hoại gợi ý (agent được chọn bước khác nếu hợp lý hơn, nhưng phải nói rõ):

| Test | Phá |
|---|---|
| `..._ghi_log_truoc_doc_holdout_sau` | Trong `main()` của `scripts/screen_vn30f_orderbook.py`, đưa `load_holdout_sessions` lên trước `_write_holdout_log` |
| `test_forecast_recovers_volatility_level` | Làm `forecast_sigma` trả về sigma nhân 2 |
| `test_qua_200_tin_...` | Đổi giới hạn hàng đợi 200 thành 201, hoặc bỏ dòng thông báo "đã bỏ" |
| hai test `nav_reread` | Bỏ đọc lại NAV, hoặc bỏ cảnh báo, đúng điều test tuyên bố |
| hai test `scripts_convention` | Thêm một script mồ côi tạm `scripts/zz_mo_coi.py` (xóa sau khi xong) |

## 4. Hoàn thành khi
- Bảng §1 bước 1 đủ 7 dòng có số đo.
- Mỗi test được sửa có: thời gian trước và sau, bước phá hoại, tên test đỏ.
- **Mục tiêu:** tổng thời gian 7 test ở §0 giảm **ít nhất một nửa** so với 121 giây đo ngày 08/10, đo trên cùng máy, hai lần. Không đạt thì báo rõ chỗ nghẽn còn lại; không lấy test khác bù vào.
- Bộ đầy đủ: số test **không đổi (1919)**, không test nào đỏ.
- `uv run ruff check trading tests scripts` sạch.
- `detect_changes` chỉ gồm file test (cộng dòng thống kê GitNexus trong `AGENTS.md`/`CLAUDE.md` nếu `analyze` tự sửa).

## 5. Báo cáo cho Claude
1. Bảng đo nguyên nhân 7 test, kèm đúng/sai cho từng nghi vấn ở §0.
2. Bảng sửa: test, cách sửa, giây trước/sau, bước phá hoại, tên test đỏ.
3. Dòng tổng và bảng `--durations=25` của hai lần chạy cả bộ.
4. Test nào cần sửa code sản phẩm mới nhanh được: đề xuất, số giây, rủi ro. Không tự làm.
5. Output `detect_changes`; mọi chỗ phải tự diễn giải.
