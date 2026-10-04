# Quy ước và phân loại thư mục `scripts/`

Tài liệu này ghi nhận quy ước đặt tên và cách sử dụng các script trong thư mục `scripts/`. **Đọc kỹ trước khi dọn dẹp hoặc phân loại bất kỳ script nào.**

---

## 1. Bảng quy ước tiền tố

| Tiền tố | Vai trò | Tính chất | Cách sử dụng |
|---|---|---|---|
| **`.probe_*`** | Thăm dò vận hành chuyên sâu | Chỉ đọc (read-only), an toàn | Chẩn đoán nguyên nhân gốc khi hệ thống có dấu hiệu bất thường (ví dụ: sức mua tài khoản, HII câm, tick gap). Giữ lại để lặp lại phép đo đối chứng. |
| **`.spike_*`** | Thử nghiệm nghiên cứu / backtest | Throwaway, độc lập | Chạy kiểm định giả thuyết mới hoặc đo đạc chiến lược mà không can thiệp vào code production. Giữ lại làm bằng chứng cho các kết luận kỹ thuật. |
| **`.repro_*`** | Tái hiện bug (reproduction) | Cô lập, có chủ ý | Dựng lại chính xác điều kiện biên gây lỗi (ví dụ flake NATS) để phục vụ debug và viết test chặn hồi quy. |
| **Không dấu chấm** | Công cụ vận hành production / SDK | Chạy định kỳ hoặc CLI | Được `scripts/sched.sh`, test suite, hoặc tài liệu vận hành gọi trực tiếp. **LƯU Ý — đọc kỹ cơ chế, đừng chỉ đọc kết luận:** `spike_ssi_sdk_auth.py`, `spike_ssi_symbols_classify.py` và `spike_ssi_sdk_derivative_ohlc_stream.py` **không** được `import` ở bất kỳ đâu. Chúng là **bước trong runbook vận hành**: `heartbeat_check.py:308,314` và `load_token_to_db.py:2,6,31` nhắc tên chúng trong **thông báo lỗi** để bảo người vận hành phải chạy gì; `collector/backfill.py:305` nhắc tên trong một **comment**; còn `backfill_universe.py:49` đọc **file dữ liệu** `.spike_all_symbols_classified.json` chứ không gọi script sinh ra nó. Tương tự, `fix_mojibake.py` và `scan_mojibake.py` là các công cụ bảo trì chính thức (bỏ dấu chấm từ đợt 60), dùng khi phát hiện lỗi mã ký tự do xung đột cp1252/UTF-8 trên Windows. Xoá chúng thì code vẫn chạy — cái hỏng là mọi câu hướng dẫn trỏ vào hư không, và không ai dựng lại được token, bảng phân loại mã hay khắc phục encoding khi gặp sự cố. **KHÔNG XOÁ.** |

---

## 2. Cảnh báo quan trọng về "Tham chiếu"

> **"0 tham chiếu" KHÔNG có nghĩa là bỏ đi được.**
>
> 1. **Dấu chấm đầu tên mang hai ý nghĩa bắt buộc: "giữ có chủ ý cho môi trường dev, không nối vào pipeline" VÀ "không ship vào git / không đưa lên VPS production"** (được tự động loại trừ bởi `.gitignore`). Mọi công cụ chẩn đoán hoặc vận hành cần thiết trên môi trường VPS PHẢI là script chính thức không mang dấu chấm đầu tên (ví dụ `scripts/probe_dead_man_switch.py`, hoặc được mở ngoại lệ tường minh `!` trong `.gitignore`). Các công cụ mang dấu chấm được thiết kế để người vận hành chạy thủ công khi cần chẩn đoán sự cố tại máy dev, không phải để `import` trong code.
> 2. Phần lớn tham chiếu tới nhóm script này là **chuỗi thông báo hướng dẫn người vận hành** (nằm trong docstring, log hoặc thông báo lỗi) bảo người vận hành phải chạy lệnh gì. Công cụ phân tích mã tĩnh sẽ không thấy `import` nào.
> 3. Nhiều script và file dữ liệu đi kèm có quan hệ chéo: ví dụ `scripts/backfill_universe.py` đọc trực tiếp file dữ liệu `scripts/.spike_all_symbols_classified.json`, trong khi script sinh ra file đó (`spike_ssi_symbols_classify.py`) chỉ xuất hiện trong câu hướng dẫn.

---

## 3. Quy tắc khi muốn loại bỏ script

Trước khi đề xuất xoá bất kỳ file nào trong `scripts/`:
1. **Kiểm tra tham chiếu toàn diện:** Quét chuỗi tên file trong `scripts/`, `trading/`, `tests/`, `docs/` và các file cấu hình.
2. **Đọc nội dung và docstring:** Xác nhận mục đích lịch sử của file đó trước khi kết luận nó là rác.
3. **Chỉ người phụ trách/chủ dự án mới có quyền xoá.** Mọi đề xuất dọn dẹp phải lập danh sách và nêu rõ lý do trong báo cáo nghiên cứu.


---

## 4. Khai báo script không do `sched.sh` gọi và không do `tests/` dùng (đợt 159)

> **Đối chiếu với đợt 53 (18/09) — bắt buộc đọc trước khi xoá bất cứ gì.** Báo cáo
> `docs/superpowers/research/2026-09-18-dot-53-don-rac-va-kiem-dinh-image.md` §5.1 đã kiểm kê theo tham chiếu
> và kết luận **28 script là CÔNG CỤ GIỮ CÓ CHỦ Ý**, 5 script CẦN NGƯỜI QUYẾT. Claude đối chiếu khi audit đợt 159:
> **8 dòng** ban đầu ghi `KHÔNG RÕ` đã được đợt 53 kết luận giữ có chủ đích, nên đã đổi thành `CÒN CẦN`:
> `spike_securities_summary_raw`, `spike_ssi_sdk_account`, `spike_ssi_sdk_equity_10y_history`, `spike_ssi_sdk_hnx_upcom_ohlc`, `spike_ssi_sdk_index_lookup`, `spike_ssi_sdk_index_stream`, `spike_ssi_sdk_index_summary`, `spike_ssi_sdk_ohlc`.
> Vì vậy **`KHÔNG RÕ` không phải danh sách để xoá** — nó là danh sách cần đối chiếu tiếp.

Quy ước ở mục 1 nói "không dấu chấm = công cụ chính thức", nhưng nhiều script không dấu chấm không được
`scripts/sched.sh` gọi và cũng không được `tests/` nhập hoặc gọi. Test
`tests/test_scripts_convention.py` bắt buộc **mỗi** script `.py` không dấu chấm (bỏ qua `_*.py`) phải thuộc
một trong ba nhóm: (1) được `sched.sh` gọi, (2) được `tests/*.py` nhắc tên, (3) **có một dòng trong bảng
dưới đây**. Thêm script mới thuộc nhóm 3 mà quên khai báo thì test đỏ và nêu đúng tên file.

Cột trạng thái (chỉ ba giá trị):
- **CÒN CẦN**: có một chỗ vận hành còn trỏ vào nó (tài liệu vận hành, thông báo lỗi, comment/docstring của code đang chạy).
- **ĐÃ GHI SỐ ĐO**: bằng chứng là một báo cáo đã lưu kết quả chạy của nó. Script chỉ còn để chạy lại.
- **KHÔNG RÕ**: không tìm thấy bằng chứng còn cần (chỉ thấy trong kế hoạch/prompt cũ, hoặc không thấy ở đâu). Đây là kết luận hợp lệ, **không** có nghĩa là bỏ đi được (xem mục 2) và **không** phải đề xuất xoá (xem mục 3).

Bằng chứng là `đường-dẫn:số-dòng` đo ngày 04/10/2026. Số dòng có thể trôi khi tài liệu được sửa; test chỉ
kiểm file được dẫn **còn chứa tên script**.

| Script | Vai trò | Trạng thái | Bằng chứng |
|---|---|---|---|
| `backfill_spike_data_to_db` | Ghi dữ liệu spike 5 phút từ file JSON vào bảng `bars`, có kiểm tra trùng. | KHÔNG RÕ | Chỉ thấy trong `docs/prompts/` và `docs/superpowers/research/2026-09-26-dot-108-engine-bo-nen-ban-va-don-nen-gia-0.md:207` (nhắc như nơi đếm nến giá 0). |
| `backtest_to_db` | Chạy mô phỏng chiến lược từng mã rồi ghi DB cho Grafana đọc. | KHÔNG RÕ | Chỉ có kế hoạch tạo nó: `docs/superpowers/plans/2026-08-30-backtest-grafana.md:13`. |
| `bingx_account_probe` | Thăm dò tài khoản BingX Perpetual, chỉ đọc. | KHÔNG RÕ | Chỉ có kế hoạch tạo nó: `docs/superpowers/plans/2026-09-27-brief-dot-111-bingx-ket-noi-chi-doc.md:45`. |
| `check_orders_hygiene` | Báo cáo vệ sinh bảng `orders` (mã lạ), không xoá gì. | ĐÃ GHI SỐ ĐO | Output chạy thật: `docs/superpowers/research/2026-09-18-dot-49-mo-rong-hop-dong-va-nguong-luong.md:172`. |
| `check_price_adjustment` | Kiểm tra `bars_daily` đã điều chỉnh chia tách chưa, xuất danh sách mã loại trừ (`--emit-exclusions`). | CÒN CẦN | Code đang chạy trỏ vào làm nguồn file loại trừ: `scripts/measure_strategy.py:33`, `scripts/score_sepa_daily.py:323`. |
| `check_real_order_readiness` | Báo cáo mức sẵn sàng của đường lệnh thật. | CÒN CẦN | Đợt 150 chạy nó để nghiệm thu: `docs/superpowers/research/2026-10-03-dot-150-chuyen-lenh-that-sang-0434226.md:44`; toàn văn output đợt 48: `docs/superpowers/research/2026-09-18-dot-48-hop-dong-sdk.md:94`. |
| `check_refprice_reset` | Đối chiếu 10 mã đã biết về việc reset giá tham chiếu. | KHÔNG RÕ | Chỉ nhắc trong kế hoạch: `docs/superpowers/plans/2026-08-18-data-completeness.md:12`. |
| `classify_overnight_gaps` | Phân loại 837 bước nhảy giá qua đêm (> 25%). | KHÔNG RÕ | Chỉ nhắc trong kế hoạch: `docs/superpowers/plans/2026-08-18-data-completeness.md:13`. |
| `fix_backfill_progress` | Sửa `backfill_progress` cho khớp thực tế (xem trước, rồi `--apply`). | CÒN CẦN | Runbook: `DEPLOYMENT.md:729`. |
| `fix_mojibake` | Gỡ mojibake nhiều lớp (UTF-8 bị đọc nhầm thành cp1252). | CÒN CẦN | Mục 1 của chính tài liệu này nêu là công cụ bảo trì chính thức: `scripts/README.md:14`. |
| `measure_cross_sectional` | CLI đo chiến lược động lượng cắt ngang 20 mã (đợt 39). | KHÔNG RÕ | Chỉ nhắc như một nơi gọi `read_crypto_bars`: `docs/superpowers/research/2026-09-28-dot-121-bit-hai-cong-mo-san.md:520`. Báo cáo đợt 39 giữ số đo nhưng không nêu tên script. |
| `measure_octopus_combo_matched_basket` | Đo OctopusComboStrategy trên đường ống `run_backtest` (đợt 8). | ĐÃ GHI SỐ ĐO | `docs/superpowers/research/2026-09-06-dot-8-octopus-combo-registry-report.md:52`. |
| `measure_perp_modules` | CLI đo hai module perpetual 1H, chia IS/OOS (đợt 37). | ĐÃ GHI SỐ ĐO | `docs/superpowers/research/2026-09-12-dot-37-do-hai-module-perp-1h-price-only.md:10`. |
| `measure_session_stream_metrics` | Đo chỉ số chốt nến thời gian thực phiên chiều. | ĐÃ GHI SỐ ĐO | `docs/superpowers/research/2026-09-14-dot-43-luong-ssi-va-nghiem-thu-phien-chieu.md:47`; các phiên đo kế tiếp: `docs/superpowers/research/2026-09-15-dot-44-dem-snapshot-va-chay-lai-event-study.md:50`. |
| `param_sensitivity` | Kiểm định độ nhạy tham số cho Octopus Pullback (đợt 9). | ĐÃ GHI SỐ ĐO | Output chạy: `docs/superpowers/research/2026-09-06-dot-9-chuan-hoa-phep-do-backtest-report.md:171`. |
| `probe_account_balance_22h` | Thăm dò phản hồi account balance SSI trong khung 22h. | CÒN CẦN | Bước kiểm số dư 22h còn trong việc đang làm: `docs/superpowers/research/2026-10-03-dot-150-chuyen-lenh-that-sang-0434226.md:184`, `docs/superpowers/research/2026-10-03-dot-152-gom-viec-nho.md:55`. |
| `probe_bars_5m_completeness` | Đo độ đầy đủ của nến 5 phút, chỉ đọc. | CÒN CẦN | Dùng để kiểm nến giá 0: `docs/superpowers/research/2026-09-26-dot-108-engine-bo-nen-ban-va-don-nen-gia-0.md:252`. |
| `probe_dead_man_switch` | Kiểm chứng đường Telegram và dead-man's switch ở local. | CÒN CẦN | Runbook: `DEPLOYMENT.md:1111`. |
| `probe_engine_consumer` | Đọc trạng thái consumer `engine` trên JetStream stream `BARS`. | KHÔNG RÕ | Chỉ có kế hoạch tạo nó: `docs/superpowers/plans/2026-09-09-brief-dot-24-quan-sat-trong-phien.md:130`. Việc tương tự đã có `engine_consumer_check.py` (do `sched.sh` gọi); chưa kiểm xem nó thay thế hẳn chưa. |
| `probe_ssi_5m_0607` | Điều tra nguyên nhân mất nến 5 phút ngày 06 và 07/07/2026 tại SSI (đợt 14). | ĐÃ GHI SỐ ĐO | `docs/superpowers/research/2026-09-07-dot-14-vps-pipe-and-missing-bars-report.md:106`. |
| `probe_timestamp_semantics` | Đo hướng ngữ nghĩa timestamp (đợt 72, lớp vỏ cho công cụ đợt 42). | CÒN CẦN | Code đang chạy trỏ vào: `scripts/leakage_audit.py:4`. |
| `record_fixtures` | Ghi raw message SSI thành fixtures cho test. | CÒN CẦN | Fixtures được ghi bằng nó: `tests/fixtures/README.md:3`. |
| `scan_mojibake` | Quét file văn bản trong repo tìm dấu vết mojibake. | CÒN CẦN | `scripts/README.md:14`. |
| `screen_liquidity` | Lọc thanh khoản từ `bars_daily` sang `symbol_universe.is_active`. | CÒN CẦN | `GO_LIVE_AUDIT.md:490`. |
| `spike_securities_status_check` | Thăm dò SSI có trả trạng thái "hạn chế giao dịch" không (chỉ đọc). | KHÔNG RÕ | Không tài liệu nào nhắc ngoài brief đợt 159. |
| `spike_securities_summary_raw` | Kiểm khả thi endpoint tóm tắt chứng khoán (bước 0 của prompt 15/08). | CÒN CẦN | Chỉ nhắc trong kế hoạch/prompt cũ và một báo cáo dọn rác ghi "giữ có chủ ý" (quyết định giữ, không phải bằng chứng còn cần): `docs/superpowers/research/2026-09-18-dot-53-don-rac-va-kiem-dinh-image.md:215`. |
| `spike_ssi_history_depth` | Đo độ sâu lịch sử SSI và liệt kê mã 3 sàn. | ĐÃ GHI SỐ ĐO | `docs/superpowers/research/2026-08-09-ssi-history-depth.md:4`. |
| `spike_ssi_sdk_account` | Phase 0 spike: xác nhận Portfolio/Account API thật (số dư, vị thế). | CÒN CẦN | Chỉ được `scripts/spike_ssi_sdk_derivative_account.py:232` nhắc trong comment làm mẫu, và trong `docs/plans-legacy/`. |
| `spike_ssi_sdk_derivative_account` | Phase 0 spike: tài khoản phái sinh thật (VN30F1M). | CÒN CẦN | Bảng OI chép tay lấy từ nó: `scripts/measure_derivative_contract_volume.py:35`. |
| `spike_ssi_sdk_derivative_ohlc_stream` | Phase 0 spike: OHLC và stream thật cho VN30F1M. | CÒN CẦN | Mục 1 của tài liệu này: `scripts/README.md:14`; code đang chạy: `trading/collector/backfill.py:306`. |
| `spike_ssi_sdk_equity_10y_history` | Phase 0 spike: lấy dữ liệu ngày 10 năm cho cổ phiếu 3 sàn. | CÒN CẦN | Chỉ nhắc trong `docs/prompts/PROMPT_EXECUTE_HISTORICAL_DATA_SPIKE.md:38`. |
| `spike_ssi_sdk_hnx_upcom_ohlc` | Phase 0 spike: lấy OHLC thật từ HNX và UPCOM. | CÒN CẦN | Chỉ nhắc trong `docs/prompts/PROMPT_EXECUTE_HNX_UPCOM_OHLC_SPIKE.md:28`. |
| `spike_ssi_sdk_index_lookup` | Spike: tra mã index thật qua `get_indexes()`. | CÒN CẦN | Chỉ được `scripts/spike_ssi_sdk_index_stream.py:16` nhắc trong comment. |
| `spike_ssi_sdk_index_stream` | Spike: xác nhận dữ liệu stream index thật từ ssi-sdk. | CÒN CẦN | Chỉ nhắc trong `docs/prompts/PROMPT_EXECUTE_COLLECTOR_INDEX_STREAMING_SPIKE.md:18`. |
| `spike_ssi_sdk_index_summary` | Spike: xác nhận `get_index_summary()` trả giá trị index thật. | CÒN CẦN | Chỉ nhắc trong kế hoạch và báo cáo dọn rác ghi "giữ có chủ ý": `docs/superpowers/research/2026-09-18-dot-53-don-rac-va-kiem-dinh-image.md:225`. |
| `spike_ssi_sdk_ohlc` | Phase 0 spike: lấy mẫu OHLC lịch sử và streaming thật từ ssi-sdk mới. | CÒN CẦN | Chỉ được `scripts/spike_ssi_sdk_account.py:7` nhắc trong comment làm mẫu. |
| `spike_ssi_symbols_classify` | Khám phá trường phân loại của `get_securities_info_by_board`, sinh `.spike_all_symbols_classified.json`. | CÒN CẦN | Runbook: `DEPLOYMENT.md:718`; thông báo lỗi: `scripts/backfill_universe.py:52`. |
| `verify_backup_file_roundtrip` | Kiểm chứng mắt xích cuối của đường dữ liệu VPS: `backup_db.sh` qua ống host (đợt 14). | ĐÃ GHI SỐ ĐO | `docs/superpowers/research/2026-09-07-dot-14-vps-pipe-and-missing-bars-report.md:76`. |
| `verify_backup_restore` | Kiểm chứng quy trình sao lưu và phục hồi TimescaleDB (đợt 13). | CÒN CẦN | Được script khác nhập thật: `scripts/verify_backup_file_roundtrip.py:21`. |
| `verify_ssi_gaps` | Đối chiếu DB với API SSI để tìm khoảng trống nến. | KHÔNG RÕ | Chỉ nhắc trong prompt cũ: `docs/prompts/2026-08-15-hermes-gap-cluster.md:37`. |
