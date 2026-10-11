# Brief đợt 185 — VN30F: IS = 40 phiên hợp lệ đầu tiên (đo sớm nhất có thể, không chết vì mất phiên)

Ngày: 11/10/2026. Người giao, audit, commit, push, **chạy phép đo**: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push, KHÔNG mở `data/orderbook/`**.
Nền: commit sau `e80da41`.

## 0. Yêu cầu và cách hiểu

**Chủ dự án (11/10):** "phái sinh VN các hợp đồng có thời gian giới hạn 1 tháng cần đo sớm".

**Hợp đồng đáo hạn hằng tháng KHÔNG chặn phép đo:**
- Máy ghi tự chuyển hợp đồng. Test `test_c3_…` đã kiểm: 14/10 ra `41I1GA000`, 16/10 ra `41I1GB000`.
- Hai công cụ 162/182 đọc **mọi** thư mục hợp đồng dưới `data/orderbook/`. Sự kiện và mục tiêu nằm gọn trong một phiên (E1 kiểm `session_id`, mục tiêu chặn ở cuối khung), nên bước nhảy giá lúc roll không lọt vào số đo.
- Dữ liệu hợp đồng đã đáo hạn vẫn dùng được: lợi thế, nếu có, sẽ được giao dịch trên hợp đồng tháng gần nhất kế tiếp.

**Cái thật sự chặn là số phiên.** Phép đo cần ≥ 40 phiên IS hợp lệ.
- Thiết kế hiện tại có tập IS cố định 25/09 → 30/11, đo từ 01/12.
- Từ 25/09 đến 30/11 có 47 ngày giao dịch. Đã mất 2 phiên:
  - 29/09: file cắt cụt;
  - 01/10: không có file, log ghi `orderbook-recorder SKIP: docker chua chay`.
- Còn 36 ngày, phải có ≥ 31 phiên hợp lệ. Chỉ được mất thêm khoảng 5 phiên nữa, nếu không thì ngày 01/12 cả hai phép đo dừng ở "KHÔNG ĐỦ PHIÊN".

**Sửa thiết kế:** IS = **40 phiên hợp lệ đầu tiên kể từ 25/09**. Holdout = các phiên **sau** phiên hợp lệ thứ 40.
- Nếu không mất thêm phiên nào, phiên thứ 40 rơi vào khoảng 23–24/11, nên đo sớm được khoảng một tuần.
- Nếu mất thêm phiên, IS tự kéo dài thay vì làm phép đo chết.
- Đây là cách đo **sớm nhất** mà không hạ ngưỡng.

**Không hạ `MIN_IS_SESSIONS`.** Với khoảng 20 phiên, mỗi cặp chỉ có khoảng 50 sự kiện. Cổng mẫu ≥ 100 sự kiện chắc chắn trượt, nên đo sớm như vậy chỉ đốt dữ liệu.

**Điều kiện không nhìn trước:**
- Ranh giới phụ thuộc **tính hợp lệ** của phiên: file đọc hết, đủ phút/nến có dữ liệu. Tính hợp lệ không chứa mục tiêu, nên ranh giới không thể chọn theo kết quả.
- IS luôn là đúng 40 phiên hợp lệ **đầu tiên**. Chạy lại ngày nào cũng ra cùng tập.

**Phạm vi:**
- Chỉ đổi cách cắt IS/holdout của 162 và 182.
- Mọi thứ khác giữ nguyên: sự kiện, đặc trưng, ngưỡng, hurdle, Bonferroni, ≥ 30 phiên holdout, quy trình ghi log trước khi mở holdout.
- Đây là sửa thiết kế trước khi đo, **không** phải giả thuyết mới. Claude đã ghi spec H trước khi giao brief.

## 1. Việc agent làm

### 1.1 Hàm thuần dùng chung — `scripts/screen_vn30f_orderbook.py`
Thêm hàm:
```python
def compute_is_boundary(sessions_validity: Sequence[tuple[date, bool]], n: int = MIN_IS_SESSIONS) -> date | None:
    """Ngày của phiên hợp lệ thứ n (theo thứ tự ngày tăng dần); None nếu chưa đủ n."""
```

### 1.2 Đợt 162 — `scripts/screen_vn30f_orderbook.py`
1. **Xoá** hằng `IS_END_DATE` và `HOLDOUT_START_DATE`, gỡ khỏi `__all__` nếu có. Giữ `IS_START_DATE = date(2026, 9, 25)`.
2. `load_all_sessions(data_dir, today)`:
   - Chỉ xét file có `IS_START_DATE <= ngày < today`. File của hôm nay đang được ghi, **không mở**.
   - Duyệt file theo ngày tăng dần, mở và đánh giá từng file như hiện tại.
   - **Dừng ngay sau phiên hợp lệ thứ 40.** Không mở thêm file nào sau đó, vì đó là holdout.
   - Giữ nguyên mọi xử lý hiện có: bắt `EOFError/OSError/zlib.error` (vá đợt 182b), file ở thư mục gốc, trùng ngày giữa hai hợp đồng.
3. `count_holdout_files(data_dir, boundary, today)` và `load_holdout_sessions(data_dir, boundary, today)`: chỉ xét file có `boundary < ngày < today`.
4. `run_screening`: bỏ lọc theo `IS_END_DATE`. Tập IS là đúng các phiên hợp lệ do loader trả về.
5. `main`: thay cổng ngày bằng cổng số phiên.
   - Nạp IS rồi tính `boundary`.
   - Nếu `boundary is None`: in `CHƯA ĐỦ PHIÊN IS: k/40 phiên hợp lệ (đã kiểm tới <ngày file cuối>)` và `return 2`. Lúc này **không** gọi `run_screening` hay `compute_session_target_rows`.
   - Nếu đủ: in `Ranh giới IS: phiên hợp lệ thứ 40 = <ngày>; holdout là các phiên sau ngày này`, rồi chạy tiếp như cũ, truyền `boundary` cho phần holdout.
   - Dòng log mở holdout ghi thêm ngày ranh giới.

### 1.3 Đợt 182 — `scripts/screen_vn30f_orderflow.py`
1. Gỡ import `IS_END_DATE` và `HOLDOUT_START_DATE`. Import `compute_is_boundary` từ 162.
2. `load_is_sessions_orderflow(data_dir, today)`: áp đúng quy tắc của mục 1.2 bước 2, gồm dừng sau phiên hợp lệ thứ 40 và không mở file hôm nay. Tính hợp lệ theo quy tắc **riêng của 182** (≥ 44/48 nến có giao dịch, file đọc hết).
3. `count_holdout_files` và `load_holdout_sessions_orderflow`: nhận `boundary, today`, chỉ xét `boundary < ngày < today`.
4. `main`:
   - Thay cổng ngày bằng cổng số phiên. Chưa đủ 40 ⇒ in như mục 1.2 và `return 2`, không gọi `detect_e1/e2/e3_events`, không tính mục tiêu, không chạy kiểm đối chứng.
   - Nhánh `return 3` cũ (không đủ phiên) không còn đường tới thì xoá nó.
   - Lọc sự kiện holdout bằng `e.session_id > boundary`.
   - Dòng log mở holdout ghi thêm ngày ranh giới.
   - Sửa docstring đầu file (dòng 12) cho khớp.

Hai công cụ dùng hai quy tắc hợp lệ khác nhau, nên ranh giới của 162 và 182 **có thể khác nhau một vài ngày**. Chấp nhận: mỗi giả thuyết tự nhất quán, và holdout của mỗi bên được mở riêng.

### 1.4 Test cho ngày đáo hạn — `tests/test_record_vn30f_orderbook.py`
Thêm một test: `resolve_front_month_symbol(date(2026, 10, 15))` phải ra `"41I1GA000"`. Ngày đáo hạn vẫn ghi hợp đồng cũ.
**Không** sửa `scripts/record_vn30f_orderbook.py`.

## 2. Test bắt buộc (viết đỏ trước, rồi làm xanh)
Dùng file giả trong `tmp_path` theo đúng cấu trúc `<mã hợp đồng>/<ngày>.jsonl.gz`. Tái dùng helper sinh file giả mà test hiện có đang dùng. Đặt chung hai hợp đồng, ví dụ `41I1GA000` và `41I1GB000`, để test luôn cắt qua một lần roll.

| # | Test | Kiểm |
|---|---|---|
| T1 | `compute_is_boundary` | 39 hợp lệ ⇒ None; phiên hợp lệ thứ 40 ⇒ đúng ngày đó; phiên không hợp lệ xen giữa bị bỏ qua, không được đếm |
| T2 | 162 loader dừng | 42 file (40 hợp lệ + 1 cắt cụt xen giữa + 1 sau phiên thứ 40) và một file ngày `today`. Spy `iter_file_messages`: file sau phiên thứ 40 và file hôm nay **không bị mở**; file cắt cụt không làm sập và không được đếm |
| T3 | 162 `main` chưa đủ | 39 phiên hợp lệ ⇒ `return 2`, output có `39/40`, `run_screening` (mock) không được gọi |
| T4 | 162 holdout | `count_holdout_files` chỉ đếm `boundary < ngày < today`; không đếm file ngày `boundary` |
| T5 | 182 loader dừng | như T2, cho `load_is_sessions_orderflow` |
| T6 | 182 `main` chưa đủ | 39 phiên ⇒ `return 2`; `detect_e1_events` (spy) không được gọi |
| T7 | 182 holdout | sự kiện của ngày `boundary` không vào `h_ev_list`; sự kiện của phiên sau đó thì có |
| T8 | IS kéo dài | thiếu phiên khiến phiên hợp lệ thứ 40 rơi vào tháng 12 ⇒ IS gồm phiên tháng 12 đó, holdout bắt đầu sau nó (chứng minh không còn mốc 30/11) |
| T9 | đáo hạn | mục 1.4 |

**Test hiện có được sửa:** chỉ những test đang dùng `IS_END_DATE`, `HOLDOUT_START_DATE`, ngày `2026-12-01` / `2026-11-30` hoặc mã trả 3 của 182. Theo grep lúc viết brief, các test có thể bị ảnh hưởng:
- 162: `test_cong_ngay_chong_nhin_truoc`, `test_main_niem_phong_*` (4 test), `test_cong_mau_duoi_40_phien_is_va_duoi_100_su_kien`, `test_phien_25_09_tinh_vao_is_va_24_09_khong`;
- 182: `test_7_cong_ngay`, `test_8_niem_phong_holdout`, `test_12_…`, `test_13_khong_du_phien_is_return_3`, `test_16_…`.

Mỗi test bị sửa phải ghi trong báo cáo: sửa gì, vì sao. Test cổng ngày cũ đổi thành test cổng số phiên, **không xoá**.

**Phải giữ nguyên, không xoá, không làm yếu** (bài học đợt 183b):
- Vá `EOFError` của 182b ở cả hai loader, cùng `test_17_162_file_cat_cut_khong_sap`.
- Test đầu-cuối `test_12_dau_cuoi_is_hop_le_va_khong_mo_holdout`: vẫn chạy `main()` trọn đường IS và vẫn chứng minh không mở holdout.
- Kiểm "log đã có dòng đợt 182 ⇒ từ chối" và thứ tự ghi log **trước**, đọc holdout **sau**, ở cả hai công cụ.
- `test_c3_resolve_front_month_symbol_october_and_november`.

Agent dán `grep -c "^\(async \)\?def test" tests/test_screen_vn30f_orderbook.py tests/test_screen_vn30f_orderflow.py tests/test_record_vn30f_orderbook.py` trước và sau. Số test chỉ được tăng.

## 3. Phép phá bắt buộc
| Phép phá | Test phải đỏ |
|---|---|
| (i) loader 162 không dừng sau phiên thứ 40 | T2 |
| (ii) loader 182 mở cả file ngày `today` | T5 |
| (iii) `compute_is_boundary` đếm cả phiên không hợp lệ | T1 |
| (iv) holdout 162 dùng `>=` boundary | T4 |
| (v) lọc sự kiện holdout 182 dùng `>=` boundary | T7 |
| (vi) `main` 182 bỏ cổng số phiên (chạy tiếp khi 39) | T6 |

Sao lưu ngoài repo, khôi phục bằng `cp`, so `sha256`. Cấm `git checkout/restore/stash`. Không thêm cờ phá nào vào code sản phẩm.

## 4. Cổng kiểm cuối
- **GitNexus** (`node .gitnexus/run.cjs …`, không `npx`):
  - Trước khi sửa: chạy `impact` upstream cho `load_all_sessions`, `count_holdout_files`, `load_holdout_sessions`, `run_screening`, `main` (162), và `load_is_sessions_orderflow`, `load_holdout_sessions_orderflow`, `main` (182). Báo rủi ro. HIGH/CRITICAL thì dừng và báo.
  - Sau khi sửa: chạy `detect-changes --scope all`. Chỉ được có đúng 5 file: hai script, hai file test của chúng, và `tests/test_record_vn30f_orderbook.py`.
- `uv run pytest -m "not integration" -q` trước và sau. `uv run ruff check trading tests scripts` sạch.
- `grep -rn "HOLDOUT_START_DATE\|IS_END_DATE" scripts/screen_vn30f_orderbook.py scripts/screen_vn30f_orderflow.py tests/test_screen_vn30f_orderbook.py tests/test_screen_vn30f_orderflow.py` phải rỗng. Không sửa `scripts/screen_vn30f_intraday.py`: hằng `IS_END_DATE` ở đó là của đợt khác.

## 5. Bất biến
- **Không đọc, không liệt kê, không đếm** `data/orderbook/`. **Không** chạy `main()` của hai công cụ với `--data-dir` thật. Mọi test chỉ dùng `tmp_path`.
- **Không** ghi `docs/holdout-unlock-log.md` thật.
- **Không:** commit, push, ghi DB, đặt lệnh, chạy `scripts/sched.sh` hay script drill, đọc `.ssi_sdk_token.json` hay `.env`.
- Không sửa máy ghi, job lịch hay file nào ngoài mục 1.

## 6. Sau khi audit (Claude làm)
1. Commit, push. Ghi chú vào brief 162 và 182: "IS/holdout theo đợt 185".
2. Từ tuần sau, mỗi tuần Claude chạy hai công cụ trên dữ liệu thật để xem `k/40`. Khi chưa đủ 40, công cụ chỉ đọc tính hợp lệ, không tính mục tiêu.
3. Ngày đầu đủ 40 phiên (dự kiến khoảng 23–24/11), lượt chạy đó **là** phép đo IS chính thức, chạy một lần cho mỗi công cụ. Phán quyết theo đúng brief 162/182, không đổi ngưỡng sau khi thấy số.
4. Theo dõi roll: ngày 16/10 phải có thư mục `data/orderbook/41I1GB000/` với file 2026-10-16.

## 7. Báo cáo cho Claude
- pytest trước/sau, ruff, số test trước/sau.
- Danh sách test hiện có đã sửa, kèm lý do.
- Bảng phép phá (i)–(vi), kết quả `impact` và `detect-changes`.
- Mục "brief mơ hồ ở đâu".
- Câu chốt: *"Tôi không mở file nào trong data/orderbook/ và chưa chạy công cụ trên dữ liệu thật."*
