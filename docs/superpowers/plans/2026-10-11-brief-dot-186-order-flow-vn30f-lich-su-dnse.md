# Brief đợt 186 — Order flow VN30F trên lịch sử lệnh khớp DNSE 25/03 → 24/09/2026 (ĐĂNG KÝ TRƯỚC)

Ngày: 11/10/2026. Người giao, audit, commit, push, **chạy phép đo**: Claude. Người thực thi: agent khác.
Agent **KHÔNG** commit, **KHÔNG** push, **KHÔNG** gọi API DNSE thật, **KHÔNG** đọc `.env`, **KHÔNG** mở `data/dnse_trades/`.
Nền: commit sau `3c19786`.

## 0. Yêu cầu và cách hiểu

**Chủ dự án (11/10):** muốn biết order flow trên hợp đồng phái sinh các tháng trước có lời không, và "lấy dữ liệu hợp đồng phái sinh tháng 9".

**Sự thật đã kiểm (Claude thăm dò 11/10, chỉ gọi GET):**
- **Endpoint:** DNSE Open API (SDK PyPI `dnse` 0.5.0), `market.trades(symbol, BoardId.ROUND_LOT, from, to, limit)`, trả **từng lệnh khớp kèm `side` BUY/SELL**.
- **Mã hợp đồng:** dạng HNX `41I1G9000`. Dạng `VN30F2609` trả rỗng.
- **Tham số `from`/`to`:** epoch **giây** (ISO hoặc mili giây trả 400). Khoảng tối đa 1 ngày. `limit` tối đa 1000. Kết quả mới nhất trước.
- **`to` không gồm chính giây đó.** Phân trang bằng `to = giây cũ nhất` làm rơi 2,4% khối lượng: bản đầu của Claude mắc lỗi này. Cách đúng là `to = giây cũ nhất + 1`, rồi khử trùng lặp theo `total_volume_traded`, vốn là khối lượng lũy kế và tăng ngặt.
- **Độ đủ:** kiểm bằng khối lượng lũy kế, phiên liên tục đủ 100%. Chỉ thiếu ATO (trước 09:00) và ATC 14:45, nơi hơn 1000 lệnh khớp cùng một giây.
- **Lịch sử là cửa sổ trượt khoảng 200 ngày.** Ngày 11/10, ngày sớm nhất còn lấy được là 25/03/2026. Vì vậy Claude đã **tải thô ngay** 25/03 → 24/09 bằng script tạm trong thư mục nháp, lưu ở `data/dnse_trades/<mã>/<ngày>.jsonl.gz` kèm `_manifest.jsonl`.
- **Định dạng một dòng file**, sắp theo `total_volume_traded` tăng dần:
  ```json
  {"market_id": "DVX", "board_id": "G1", "isin": "VN41I1G40007", "symbol": "41I1G4000", "match_price": 1809.9, "match_qtty": 1, "side": "BUY", "avg_price": 1809.9, "total_volume_traded": 227, "gross_trade_amount": 41.08473, "highest_price": 1809.9, "lowest_price": 1809.9, "open_price": 1809.9, "time": "2026-03-25 09:00:00.128"}
  ```

**Phép thử:**
- Đúng ba sự kiện của đợt 182 v2 (E1 phân kỳ CVD, E2 phân kỳ delta trong nến, E3 hấp thụ → khởi xướng) × chân trời 15/30 phút, tức 6 cặp.
- Tham số giữ y nguyên 182, đo trên khoảng 127 phiên **chưa ai nhìn**, tách rời hoàn toàn tập IS của 162/182 (bắt đầu 25/09).
- **Đây không phải giả thuyết mới.** Đây là lần kiểm độc lập thứ hai của giả thuyết 9. Đợt 182 vẫn đo nguyên trạng trên dữ liệu máy ghi, **không** đổi gì theo kết quả 186.

**Không có đường tới lệnh thật.** Nếu ĐẠT, bước sau là một brief riêng để chạy giấy trên dữ liệu trực tiếp.

## 1. Thiết kế đo (khoá trước, không đổi sau khi thấy số)

### 1.1 Cửa sổ
| Tập | Phiên | Ước tính |
|---|---|---|
| CHÍNH | 2026-03-25 → 2026-06-30 | khoảng 67 phiên |
| LẶP LẠI | 2026-07-01 → 2026-09-24 | khoảng 60 phiên |

- Mỗi ngày chỉ dùng hợp đồng tháng gần nhất, tức file nằm trong thư mục mã do `front_month_symbol(ngày)` trả về (mục 2.1).
- Công cụ **không bao giờ mở** file có ngày ≥ `IS_START_DATE` (25/09), import từ `scripts/screen_vn30f_orderbook.py`.

### 1.2 Phiên hợp lệ
Phiên hợp lệ khi đủ **cả ba** điều kiện:
1. File đọc hết, không `EOFError/OSError/zlib.error/json` lỗi.
2. Khối lượng thiếu **trong phiên liên tục** ≤ 0,5% tổng khối lượng phiên (định nghĩa ở mục 2.2).
3. ≥ `VALID_BARS_THRESHOLD` (44/48) nến có giao dịch, đúng quy tắc của 182.

Cần ≥ 40 phiên hợp lệ ở CHÍNH và ≥ 30 ở LẶP LẠI. Thiếu thì in `KHÔNG ĐỦ PHIÊN` và `return 3`, **không nới**.

### 1.3 Dựng nến và sự kiện: dùng lại 182, không gõ lại
- Chuyển mỗi dòng DNSE thành tin dạng máy ghi SSI rồi đưa vào `build_footprint_bars_and_trades` của 182, không sửa hàm đó. Quy tắc chuyển:
  - `{"type": "TRADE", "price": match_price, "quantity": match_qtty, "side": ..., "trading_time": time[:19]}`;
  - `side`: BUY → `"B"`, SELL → `"S"`, còn lại → `"U"` (182 tự loại);
  - `time[:19]` cắt phần mili giây, vì `parse_trading_time` nhận `%Y-%m-%d %H:%M:%S`.
  - Đưa vào theo đúng thứ tự file (khối lượng lũy kế tăng dần) để giữ thứ tự trong cùng giây.
- Dùng lại nguyên các hàm của `scripts/screen_vn30f_orderflow.py`: `build_price_lookup`, `detect_e1_events`, `detect_e2_events`, `detect_e3_events`, `calculate_event_targets`, `filter_non_overlapping_events`, `block_bootstrap_p_value` (n_bootstrap=2000, seed=42), `check_control_variable_orderflow`, `compute_economic_hurdle`, `evaluate_pair_criteria`. Import, không chép.
- **Phát hiện sự kiện một lần** trên toàn bộ nến hợp lệ CHÍNH + LẶP LẠI theo thời gian, rồi chia sự kiện theo `session_id`. Ngưỡng E2 lấy từ 5 phiên trước, nên 5 phiên đầu LẶP LẠI dùng 5 phiên cuối CHÍNH. Đó vẫn là quá khứ. E1/E3 vốn nằm gọn trong một phiên.
- Mục tiêu và giá thoát tra trong đúng phiên của sự kiện (`lookup` theo ngày), như 182.

### 1.4 Thống kê và phán quyết
1. **Kiểm đối chứng:** Spearman ρ giữa delta và close − open cùng nến, trên nến CHÍNH, phải > 0,3. Không đạt ⇒ in `DỮ LIỆU SIDE KHÔNG ĐÁNG TIN`, `return 4`, không in bảng.
2. **Hurdle:** `compute_economic_hurdle(trung vị close CHÍNH)`. **Cùng một hurdle** dùng cho LẶP LẠI, không tính lại.
3. **CHÍNH:** mỗi cặp dùng `evaluate_pair_criteria`, mặc định 182: ≥ 100 sự kiện, mỗi hướng ≥ 30, p một phía < 0,05/6, trung bình y ≥ hurdle.
4. **LẶP LẠI:** chỉ xét k cặp ĐẠT ở CHÍNH. Mỗi cặp ĐẠT khi p một phía < 0,05/k **và** trung bình y ≥ hurdle (của CHÍNH). Không đòi ≥ 100 sự kiện.
5. **Phán quyết:** cặp ĐẠT khi qua cả CHÍNH lẫn LẶP LẠI. In bảng 6 cặp cho từng tập: N, N mua, N bán, trung bình y, hurdle, p, kết quả. Nếu k = 0 thì in `LẶP LẠI: không có cặp nào để kiểm`.
6. **Dự đoán ghi trước:** không cặp nào ĐẠT.

## 2. Việc agent làm

### 2.1 `scripts/fetch_dnse_vn30f_trades.py` (mới): đưa script tải tạm vào repo, có test
- **`front_month_symbol(d: date) -> str`:** dùng `generate_vn30_candidate_contracts` của `scripts/record_vn30f_orderbook.py` và `identify_front_month` của `scripts/measure_derivative_contract_volume.py`. **Không** viết lại hàm thứ Năm thứ 3.
- **`fetch_session_trades(client, symbol, d, sleep_fn=time.sleep) -> tuple[list[dict], dict]`:** phân trang như mục 0.
  - Khung `from` = 08:30, `to` = 15:05 giờ VN của ngày `d`, `limit=1000`.
  - Lật trang bằng `to = floor(giây cũ nhất của trang) + 1`. Khử trùng lặp theo `total_volume_traded`.
  - Nếu một trang không thêm lệnh mới nào (hơn 1000 lệnh trong một giây) thì `to = giây đó` và tăng `stuck_seconds`.
  - Dừng khi trang có < 1000 lệnh, khi `to <= from`, hoặc khi vượt 3000 lần gọi.
  - Mỗi lần gọi xong thì `sleep_fn(1.1)`. Lỗi gọi thì thử lại tối đa 5 lần, chờ 30 s × lần thử.
  - Trả về các dòng `model_dump(mode="json", exclude_none=True)` sắp theo `total_volume_traded`, kèm `info`.
- **`volume_continuity(rows) -> dict`:** tính `total_volume`, `missing_continuous`, `missing_outside`.
  - Khoảng thiếu ở dòng i là `tv[i] − tv[i−1] − qtty[i]` (với i = 0 thì tv[−1] = 0). Thiếu thì cộng phần dương.
  - Khoảng thiếu tính vào `missing_continuous` khi dòng i−1 có giờ ≥ 09:00:00 **và** dòng i có giờ < 14:30:00. Mọi khoảng thiếu khác, gồm khoảng thiếu ở dòng đầu tiên (ATO), tính vào `missing_outside`.
- **Ghi file:** `<out>/<mã>/<ngày>.jsonl.gz`, đúng định dạng mục 0. Ghi file `.tmp` trước rồi `os.replace`. Phiên đã có file thì bỏ qua. Mỗi phiên thêm một dòng vào `<out>/_manifest.jsonl`, gồm `date, symbol, n_trades, total_volume, missing_continuous, missing_outside, stuck_seconds, calls`.
- **CLI:**
  - `--from YYYY-MM-DD --to YYYY-MM-DD --out data/dnse_trades`. Chỉ ngày thứ Hai đến thứ Sáu. Ngày không có lệnh nào (nghỉ lễ) thì không ghi file, manifest ghi `n_trades: 0`.
  - **Từ chối** `--to >= IS_START_DATE`: `return 2`, không tạo client.
  - Key lấy bằng `scripts._db_common.load_dotenv()` rồi `os.environ["PRODUCT_DNSE_API_Key"]` / `["PRODUCT_DNSE_API_Secret"]`. **Không bao giờ in giá trị.**
  - **`--verify`:** không gọi mạng. Đọc lại mọi file trong `--out`, tính `volume_continuity` và in bảng: ngày, mã, số lệnh, các loại khối lượng thiếu. Mã thoát 1 nếu có phiên `missing_continuous` > 0,5%.
- **Phụ thuộc:** `uv add dnse==0.5.0`, chỉ thêm gói này, đúng phiên bản. Import `dnse` **bên trong** hàm tạo client, để test và `--verify` không cần mạng.

### 2.2 `scripts/screen_vn30f_orderflow_dnse.py` (mới): công cụ đo của mục 1
- **Loader:** `load_dnse_sessions(data_dir, start, end) -> list[OrderFlowSession]`, dùng lại dataclass `OrderFlowSession` của 182.
  - Duyệt ngày trong `[start, end]`. Mỗi ngày chỉ mở file `<data_dir>/<front_month_symbol(ngày)>/<ngày>.jsonl.gz`.
  - Ngày ≥ `IS_START_DATE` thì bỏ qua **mà không mở**.
  - Áp quy tắc hợp lệ mục 1.2. Lý do không hợp lệ ghi vào `invalid_reason`: `file hỏng`, `thiếu KL liên tục x%`, `phiên thưa (n/48 nến)`.
- **`dnse_row_to_message(row) -> dict`:** theo mục 1.3.
- **`run_dnse_screening(data_dir) -> dict`** và **`main(args) -> int`:** in số phiên hợp lệ / không hợp lệ (kèm lý do) của từng tập, ρ đối chứng, hurdle, hai bảng và phán quyết.
  - Mã thoát: 0 xong; 3 không đủ phiên; 4 đối chứng hỏng.
  - **Không có cổng ngày.** Phép đo do Claude chạy, mục 6.
- Hằng mới chỉ gồm: `MAIN_START = date(2026, 3, 25)`, `MAIN_END = date(2026, 6, 30)`, `REPEAT_START = date(2026, 7, 1)`, `REPEAT_END = date(2026, 9, 24)`, `MAX_MISSING_CONTINUOUS_RATIO = 0.005`, `MIN_MAIN_SESSIONS = 40`, `MIN_REPEAT_SESSIONS = 30`.

### 2.3 Không được sửa
- `scripts/screen_vn30f_orderflow.py`, `scripts/screen_vn30f_orderbook.py`, `scripts/record_vn30f_orderbook.py`, `scripts/measure_derivative_contract_volume.py`, `scripts/_db_common.py`;
- mọi file trong `trading/`;
- mọi file test hiện có.
Nếu thấy cần sửa một trong số đó thì **dừng và báo**.

## 3. Test bắt buộc (viết đỏ trước, rồi làm xanh)
Hai file test mới: `tests/test_fetch_dnse_vn30f_trades.py` và `tests/test_screen_vn30f_orderflow_dnse.py`. Chỉ dùng `tmp_path` và client giả. Client giả mô phỏng đúng ba tính chất của API thật: mới nhất trước, `limit` ≤ 1000, `to` không gồm giây đó.

| # | Test | Kiểm |
|---|---|---|
| 1 | `front_month_symbol` | 25/03 → `41I1G4000`; 16/04 (đáo hạn) → `41I1G4000`; 17/04 → `41I1G5000`; 17/09 → `41I1G9000`; 18/09 → `41I1GA000` |
| 2 | phân trang | 3.500 lệnh giả, nhiều giây có 3–5 lệnh nằm vắt qua ranh giới trang ⇒ đủ đúng 3.500, không trùng; `volume_continuity` ra `missing_continuous == 0` |
| 3 | giây kẹt | 1.200 lệnh cùng giây 14:45:00 ⇒ hàm kết thúc, `stuck_seconds ≥ 1`, phần thiếu nằm ở `missing_outside` |
| 4 | liên tục | khoảng thiếu ở dòng đầu (ATO) ⇒ `missing_outside`; khoảng thiếu ở 10:00 ⇒ `missing_continuous`; khoảng thiếu ở 14:45 ⇒ `missing_outside` |
| 5 | từ chối ngày | `--to 2026-09-25` ⇒ `return 2`, hàm tạo client (mock) không được gọi |
| 6 | ghi file | phiên đã có file thì bỏ qua (client không được gọi); lỗi giữa chừng không để lại file `.gz` dở |
| 7 | không lộ key | env giả có key `KHOA_BI_MAT_123` và client giả ⇒ stdout/stderr không chứa chuỗi đó |
| 8 | chuyển dòng | BUY → B, SELL → S, UNSPECIFIED → U; giờ cắt mili giây; ba dòng tự dựng cho delta nến đúng bằng tay; dòng U không vào delta |
| 9 | hợp lệ | thiếu khối lượng liên tục 0,6% ⇒ không hợp lệ, có lý do; 0,4% ⇒ hợp lệ; < 44 nến ⇒ không hợp lệ; file cắt cụt ⇒ không hợp lệ, không sập |
| 10 | dùng lại 182 | `mod.detect_e1_events is screen_vn30f_orderflow.detect_e1_events`, tương tự cho các hàm ở mục 1.3 |
| 11 | phán quyết | dựng kết quả giả: cặp qua CHÍNH nhưng trượt LẶP LẠI ⇒ TRƯỢT; qua cả hai ⇒ ĐẠT; với k = 2, p LẶP LẠI = 0,03 ⇒ TRƯỢT (vì 0,03 > 0,025); hurdle LẶP LẠI là hurdle CHÍNH, kể cả khi trung vị giá LẶP LẠI khác |
| 12 | đối chứng | delta ngược dấu close − open ⇒ `return 4`, không in bảng |
| 13 | đầu-cuối | xem bên dưới |

**Chi tiết test 13 (đầu-cuối):**
- Dựng file DNSE giả trong `tmp_path`: 41 phiên CHÍNH và 31 phiên LẶP LẠI hợp lệ, delta cùng dấu close − open; 1 phiên thưa; 1 phiên thiếu khối lượng liên tục; hai thư mục hợp đồng; 1 file ngày 2026-09-25 cố ý hỏng.
- `main()` phải `return 0`; in đủ 6 cặp ở CHÍNH; báo đúng hai phiên không hợp lệ kèm lý do.
- Spy hàm mở file: file 2026-09-25 **không bị mở**.

## 4. Phép phá bắt buộc
| Phép phá | Test phải đỏ |
|---|---|
| (a) lật trang `to = giây cũ nhất` (bỏ `+ 1`) | 2 |
| (b) đổi BUY ↔ SELL khi chuyển dòng | 8 |
| (c) bỏ kiểm `--to >= IS_START_DATE` | 5 |
| (d) tính khoảng thiếu ATO vào `missing_continuous` | 4 |
| (e) LẶP LẠI dùng α = 0,05 thay vì 0,05/k | 11 |
| (f) LẶP LẠI tính lại hurdle từ giá LẶP LẠI | 11 |
| (g) loader mở cả file ≥ 25/09 | 13 |

Sao lưu ngoài repo, khôi phục bằng `cp`, so `sha256`. Cấm `git checkout/restore/stash`. Không thêm cờ phá nào vào code sản phẩm.

## 5. Cổng kiểm cuối
- **GitNexus** (`node .gitnexus/run.cjs …`, không `npx`):
  - Trước khi viết: chạy `context` cho `build_footprint_bars_and_trades`, `evaluate_pair_criteria`, `identify_front_month`, `generate_vn30_candidate_contracts`, `load_dotenv`. Chỉ đọc, không sửa.
  - Sau khi viết: chạy `detect-changes --scope all`. Chỉ được có: 2 script mới, 2 file test mới, `pyproject.toml`, `uv.lock`.
- `uv run pytest -m "not integration" -q` trước và sau. Số test chỉ được tăng.
- `uv run ruff check trading tests scripts` sạch.
- `uv run python scripts/fetch_dnse_vn30f_trades.py --to 2026-09-25 --from 2026-09-25 --out <tmp>` phải trả 2. Dán output.

## 6. Sau khi audit (Claude làm)
1. Commit, push.
2. **Kiểm dữ liệu đã tải:**
   - Chạy `fetch_dnse_vn30f_trades.py --verify --out data/dnse_trades`.
   - Phiên nào có `missing_continuous` > 0,5% thì xoá file đó và tải lại bằng công cụ mới.
   - Ghi danh sách phiên đã tải lại vào báo cáo kết quả.
3. Chạy phép đo **một lần**: `uv run python scripts/screen_vn30f_orderflow_dnse.py --data-dir data/dnse_trades`. Lưu nguyên văn output vào `docs/research/2026-10-dot-186-ket-qua-order-flow-vn30f-dnse.md`.
4. Phán quyết theo mục 1.4. **Không** đổi cửa sổ, ngưỡng, hướng hay chân trời sau khi thấy số.

## 7. Bất biến
- **Không:** gọi API DNSE thật, đọc `.env`, mở/liệt kê/đếm `data/dnse_trades/` hay `data/orderbook/`.
- **Không:** commit, push, ghi DB, đặt lệnh, gọi API BingX/SSI, chạy `scripts/sched.sh` hay script drill.
- **Không:** in key/secret, kể cả trong test hay log.
- Không xoá và không làm yếu test hiện có. Mọi test bị sửa phải báo kèm lý do; brief này không cần sửa test nào.

## 8. Báo cáo cho Claude
- pytest trước/sau, ruff, số test trước/sau.
- Bảng phép phá (a)–(g).
- Kết quả `context` và `detect-changes`.
- Output lệnh từ chối ngày.
- Mục "brief mơ hồ ở đâu".
- Câu chốt: *"Tôi không gọi API DNSE thật, không đọc .env, không mở data/dnse_trades/."*
