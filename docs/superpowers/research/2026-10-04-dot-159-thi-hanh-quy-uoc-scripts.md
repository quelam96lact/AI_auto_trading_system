# Đợt 159 — Thi hành quy ước `scripts/` bằng test, thay vì dọn tay

Nghiệm thu và đề xuất phân loại cho 116 file `.py` không dấu chấm trong `scripts/`.
**Không commit, không push. Không xoá, không đổi tên file nào trong đợt này.**

---

## 1. Phép tính phân loại và độ phủ (Tiêu chí 1)

Tổng số file `.py` không có dấu chấm đầu tên trong `scripts/`: **116 file**.

Phân rã thành các nhóm:
- **3 module dùng chung (tiền tố `_`):** `_alert_common.py`, `_db_common.py`, `_ssi_spike_common.py`.
- **113 script ứng viên chính thức:**
  1. **Nhóm 1 (được `scripts/sched.sh` gọi):** **14 script** (`backup_check`, `check_orderbook_daily`, `check_silent_engine`, `container_health_check`, `daily_data_check`, `deploy_drift_check`, `disk_check`, `docker_down_alert`, `engine_consumer_check`, `heartbeat_check`, `host_preflight`, `record_vn30f_orderbook`, `restore_drill`, `stream_health_check`).
  2. **Nhóm 2 (được `tests/` nhập hoặc gọi):** **73 script** (trong đó có toàn bộ 14 script của Nhóm 1 và 59 script chỉ xuất hiện trong test).
  3. **Nhóm 3 (không thuộc cả Nhóm 1 và Nhóm 2):** **40 script**.

### Phép tính:
$$\text{Nhóm 1 (14)} + \text{Nhóm 2 chỉ-test (59)} + \text{Nhóm 3 (40)} = 113$$
$$113 + 3 \text{ module } \_*.py = 116 \text{ (khớp 100\% tổng số script)}$$

> **Ghi chú về độ lệch số đếm (39 vs 40):**
> Trong brief, Claude ước lượng Nhóm 3 có 39 script. Khi đo thực tế bằng AST / regex quét chuỗi độc lập trên toàn bộ thư mục `tests/`:
> - Script `scripts/record_fixtures.py` được nhắc trong `tests/fixtures/README.md:3` nhưng **không** được `import` hay gọi trực tiếp trong bất kỳ file code Python nào (`tests/**/*.py`).
> - Do đó, theo định nghĩa chặt chẽ của test (chỉ quét `tests/**/*.py`), `record_fixtures` thuộc Nhóm 3, nâng tổng số script Nhóm 3 lên **40**. Khai báo mục 4 tại `scripts/README.md` đã bao phủ đầy đủ toàn bộ 40 script này.

---

## 2. Bảng khai báo 40 script Nhóm 3 trong `scripts/README.md` (Mục 4)

Thống kê theo trạng thái:
- **CÒN CẦN:** 15 script (Claude audit sửa: 13 là số đếm sai) (có runbook, tài liệu vận hành, thông báo lỗi hoặc code production đang trỏ vào).
- **ĐÃ GHI SỐ ĐO:** 8 script (kết quả chạy và đo lường đã được lưu trữ trong báo cáo nghiên cứu `docs/superpowers/research/`).
- **KHÔNG RÕ:** **17 script** (Claude audit sửa: 19 là số đếm sai) (chỉ xuất hiện trong kế hoạch cũ, prompt cũ hoặc không còn bằng chứng trỏ vào).

| Script | Vai trò | Trạng thái | Bằng chứng |
|---|---|---|---|
| `backfill_spike_data_to_db` | Ghi dữ liệu spike 5m từ JSON vào `bars` | KHÔNG RÕ | `docs/prompts/` & `research/2026-09-26-dot-108-engine-bo-nen-ban-va-don-nen-gia-0.md:207` |
| `backtest_to_db` | Chạy backtest ghi DB cho Grafana đọc | KHÔNG RÕ | Kế hoạch `plans/2026-08-30-backtest-grafana.md:13` |
| `bingx_account_probe` | Thăm dò tài khoản BingX Perpetual (chỉ đọc) | KHÔNG RÕ | Kế hoạch `plans/2026-09-27-brief-dot-111-bingx-ket-noi-chi-doc.md:45` |
| `check_orders_hygiene` | Báo cáo vệ sinh bảng `orders` (mã lạ) | ĐÃ GHI SỐ ĐO | Output chạy thật: `research/2026-09-18-dot-49-mo-rong-hop-dong-va-nguong-luong.md:172` |
| `check_price_adjustment` | Kiểm tra điều chỉnh chia tách (`--emit-exclusions`) | CÒN CẦN | Code đang chạy: `scripts/measure_strategy.py:33`, `scripts/score_sepa_daily.py:323` |
| `check_real_order_readiness` | Báo cáo sẵn sàng đường lệnh thật | CÒN CẦN | Nghiệm thu đợt 150: `research/2026-10-03-dot-150-chuyen-lenh-that-sang-0434226.md:44` |
| `check_refprice_reset` | Đối chiếu reset giá tham chiếu 10 mã | KHÔNG RÕ | Kế hoạch `plans/2026-08-18-data-completeness.md:12` |
| `classify_overnight_gaps` | Phân loại 837 bước nhảy giá qua đêm | KHÔNG RÕ | Kế hoạch `plans/2026-08-18-data-completeness.md:13` |
| `fix_backfill_progress` | Sửa `backfill_progress` cho khớp thực tế | CÒN CẦN | Runbook: `DEPLOYMENT.md:729` |
| `fix_mojibake` | Gỡ lỗi mã hoá UTF-8 / cp1252 nhiều lớp | CÒN CẦN | Quy ước công cụ bảo trì: `scripts/README.md:14` |
| `measure_cross_sectional` | CLI đo chiến lược động lượng cắt ngang 20 mã | KHÔNG RÕ | Caller `read_crypto_bars`: `research/2026-09-28-dot-121-bit-hai-cong-mo-san.md:520` |
| `measure_octopus_combo_matched_basket` | Đo OctopusComboStrategy trên `run_backtest` | ĐÃ GHI SỐ ĐO | Báo cáo: `research/2026-09-06-dot-8-octopus-combo-registry-report.md:52` |
| `measure_perp_modules` | CLI đo 2 module perpetual 1H IS/OOS | ĐÃ GHI SỐ ĐO | Báo cáo: `research/2026-09-12-dot-37-do-hai-module-perp-1h-price-only.md:10` |
| `measure_session_stream_metrics` | Đo chỉ số chốt nến real-time phiên chiều | ĐÃ GHI SỐ ĐO | Báo cáo: `research/2026-09-14-dot-43-luong-ssi-va-nghiem-thu-phien-chieu.md:47` |
| `param_sensitivity` | Kiểm định độ nhạy tham số Octopus Pullback | ĐÃ GHI SỐ ĐO | Báo cáo: `research/2026-09-06-dot-9-chuan-hoa-phep-do-backtest-report.md:171` |
| `probe_account_balance_22h` | Thăm dò phản hồi số dư SSI khung 22h | CÒN CẦN | Nghiệm thu: `research/2026-10-03-dot-150-chuyen-lenh-that-sang-0434226.md:184` |
| `probe_bars_5m_completeness` | Đo độ đầy đủ nến 5m (chỉ đọc) | CÒN CẦN | Đo nến giá 0: `research/2026-09-26-dot-108-engine-bo-nen-ban-va-don-nen-gia-0.md:252` |
| `probe_dead_man_switch` | Kiểm chứng Telegram + dead-man local | CÒN CẦN | Runbook: `DEPLOYMENT.md:1111` |
| `probe_engine_consumer` | Đọc trạng thái consumer `engine` trên NATS | KHÔNG RÕ | Kế hoạch `plans/2026-09-09-brief-dot-24-quan-sat-trong-phien.md:130` |
| `probe_ssi_5m_0607` | Điều tra mất nến 5m ngày 06-07/07/2026 SSI | ĐÃ GHI SỐ ĐO | Báo cáo: `research/2026-09-07-dot-14-vps-pipe-and-missing-bars-report.md:106` |
| `probe_timestamp_semantics` | Đo hướng ngữ nghĩa timestamp | CÒN CẦN | Code đang chạy trỏ vào: `scripts/leakage_audit.py:4` |
| `record_fixtures` | Ghi raw message SSI thành fixtures cho test | CÒN CẦN | Tài liệu fixtures: `tests/fixtures/README.md:3` |
| `scan_mojibake` | Quét phát hiện mojibake trong toàn bộ repo | CÒN CẦN | Quy ước công cụ bảo trì: `scripts/README.md:14` |
| `screen_liquidity` | Lọc thanh khoản sang `symbol_universe.is_active` | CÒN CẦN | Tài liệu nghiệm thu: `GO_LIVE_AUDIT.md:490` |
| `spike_securities_status_check` | Thăm dò SSI hạn chế giao dịch (chỉ đọc) | KHÔNG RÕ | Không có tài liệu ngoài Brief 159 |
| `spike_securities_summary_raw` | Thăm dò endpoint tóm tắt chứng khoán | KHÔNG RÕ | Báo cáo dọn rác: `research/2026-09-18-dot-53-don-rac-va-kiem-dinh-image.md:215` |
| `spike_ssi_history_depth` | Đo độ sâu lịch sử SSI + 3 sàn | ĐÃ GHI SỐ ĐO | Báo cáo: `research/2026-08-09-ssi-history-depth.md:4` |
| `spike_ssi_sdk_account` | Spike Phase 0: Portfolio/Account API | KHÔNG RÕ | Comment mẫu trong `scripts/spike_ssi_sdk_derivative_account.py:232` |
| `spike_ssi_sdk_derivative_account` | Spike Phase 0: Tài khoản phái sinh VN30F1M | CÒN CẦN | Nguồn số liệu OI: `scripts/measure_derivative_contract_volume.py:35` |
| `spike_ssi_sdk_derivative_ohlc_stream` | Spike Phase 0: OHLC/stream VN30F1M | CÒN CẦN | Code collector: `trading/collector/backfill.py:306` |
| `spike_ssi_sdk_equity_10y_history` | Spike Phase 0: Lấy 10 năm dữ liệu ngày | KHÔNG RÕ | Prompt cũ `docs/prompts/PROMPT_EXECUTE_HISTORICAL_DATA_SPIKE.md:38` |
| `spike_ssi_sdk_hnx_upcom_ohlc` | Spike Phase 0: Lấy OHLC HNX/UPCOM | KHÔNG RÕ | Prompt cũ `docs/prompts/PROMPT_EXECUTE_HNX_UPCOM_OHLC_SPIKE.md:28` |
| `spike_ssi_sdk_index_lookup` | Spike: Tra mã index SSI qua `get_indexes()` | KHÔNG RÕ | Comment trong `scripts/spike_ssi_sdk_index_stream.py:16` |
| `spike_ssi_sdk_index_stream` | Spike: Stream index từ ssi-sdk | KHÔNG RÕ | Prompt cũ `docs/prompts/PROMPT_EXECUTE_COLLECTOR_INDEX_STREAMING_SPIKE.md:18` |
| `spike_ssi_sdk_index_summary` | Spike: `get_index_summary()` REST | KHÔNG RÕ | Báo cáo dọn rác `research/2026-09-18-dot-53-don-rac-va-kiem-dinh-image.md:225` |
| `spike_ssi_sdk_ohlc` | Spike Phase 0: Sample OHLC historical/stream | KHÔNG RÕ | Comment mẫu trong `scripts/spike_ssi_sdk_account.py:7` |
| `spike_ssi_symbols_classify` | Sinh `.spike_all_symbols_classified.json` | CÒN CẦN | Runbook: `DEPLOYMENT.md:718`; lỗi: `scripts/backfill_universe.py:52` |
| `verify_backup_file_roundtrip` | Kiểm chứng backup_db.sh qua ống host (đợt 14) | ĐÃ GHI SỐ ĐO | Báo cáo: `research/2026-09-07-dot-14-vps-pipe-and-missing-bars-report.md:76` |
| `verify_backup_restore` | Kiểm chứng sao lưu/phục hồi TimescaleDB | CÒN CẦN | Caller: `scripts/verify_backup_file_roundtrip.py:21` |
| `verify_ssi_gaps` | Đối chiếu DB vs API SSI tìm gap | KHÔNG RÕ | Prompt cũ: `docs/prompts/2026-08-15-hermes-gap-cluster.md:37` |

---

## 3. Phá thử (Mutation Testing — Tiêu chí 2)

### Ca 1: Tạo script mới không khai báo (`scripts/zzz_tam_thoi_dot159.py`)
- **Dòng đỏ nguyên văn:**
  ```text
  FAILED tests/test_scripts_convention.py::test_moi_script_khong_dau_cham_thuoc_mot_trong_ba_nhom
  E       AssertionError: Script không dấu chấm không thuộc nhóm nào (không do sched.sh gọi, không do tests/ nhắc, không có dòng khai báo ở mục 4 của scripts/README.md): zzz_tam_thoi_dot159.py
  E       assert not ['zzz_tam_thoi_dot159']
  ```
- **Xoá file tạm:** Test xanh trở lại (3 passed).

### Ca 2: Xoá 1 dòng khai báo trong bảng (`verify_ssi_gaps`)
- **Dòng đỏ nguyên văn:**
  ```text
  FAILED tests/test_scripts_convention.py::test_moi_script_khong_dau_cham_thuoc_mot_trong_ba_nhom
  E       AssertionError: Script không dấu chấm không thuộc nhóm nào (không do sched.sh gọi, không do tests/ nhắc, không có dòng khai báo ở mục 4 của scripts/README.md): verify_ssi_gaps.py
  E       assert not ['verify_ssi_gaps']
  ```
- **Khôi phục `scripts/README.md`:** Hash SHA256 khớp 100%.

---

## 4. Ba danh sách đề xuất (Việc 3 — Đề xuất, KHÔNG thực hiện)

### A. Nên thêm dấu chấm (thành dev-only, rút khỏi git và không lên VPS)
Các script nghiên cứu một lần, số đo đã được ghi nhận trong tài liệu `docs/superpowers/research/`.
Chắc chắn **không ai cần trên VPS** vì môi trường production chỉ chạy daemon/collector/engine và các job theo lịch của `sched.sh`, không chạy backtest hay thăm dò sự cố quá khứ.

1. `spike_ssi_history_depth.py` $\to$ `.spike_ssi_history_depth.py`
   - *Báo cáo giữ số đo:* `docs/superpowers/research/2026-08-09-ssi-history-depth.md:4`.
   - *Lý do an toàn:* Chỉ đo độ sâu lịch sử API SSI giai đoạn khởi tạo ban đầu (tháng 8/2026).
2. `probe_ssi_5m_0607.py` $\to$ `.probe_ssi_5m_0607.py`
   - *Báo cáo giữ số đo:* `docs/superpowers/research/2026-09-07-dot-14-vps-pipe-and-missing-bars-report.md:106`.
   - *Lý do an toàn:* Phục vụ điều tra sự cố mất nến cụ thể của ngày 06 và 07/07/2026 tại SSI.
3. `verify_backup_file_roundtrip.py` $\to$ `.verify_backup_file_roundtrip.py`
   - *Báo cáo giữ số đo:* `docs/superpowers/research/2026-09-07-dot-14-vps-pipe-and-missing-bars-report.md:76`.
   - *Lý do an toàn:* Diễn tập ống backup thủ công của Đợt 14; hiện tại đã có `scripts/restore_drill.py` chạy tự động định kỳ qua cron trên VPS.
4. `measure_octopus_combo_matched_basket.py` $\to$ `.measure_octopus_combo_matched_basket.py`
   - *Báo cáo giữ số đo:* `docs/superpowers/research/2026-09-06-dot-8-octopus-combo-registry-report.md:52`.
   - *Lý do an toàn:* Đo lường backtest chiến lược Octopus Combo ở máy local dev.
5. `param_sensitivity.py` $\to$ `.param_sensitivity.py`
   - *Báo cáo giữ số đo:* `docs/superpowers/research/2026-09-06-dot-9-chuan-hoa-phep-do-backtest-report.md:171`.
   - *Lý do an toàn:* Kiểm định độ nhạy tham số backtest local.
6. `measure_perp_modules.py` $\to$ `.measure_perp_modules.py`
   - *Báo cáo giữ số đo:* `docs/superpowers/research/2026-09-12-dot-37-do-hai-module-perp-1h-price-only.md:10`.
   - *Lý do an toàn:* Đo lường backtest module perp 1H.
7. `measure_session_stream_metrics.py` $\to$ `.measure_session_stream_metrics.py`
   - *Báo cáo giữ số đo:* `docs/superpowers/research/2026-09-14-dot-43-luong-ssi-va-nghiem-thu-phien-chieu.md:47`.
   - *Lý do an toàn:* Đo lường chốt nến phiên chiều tại local trong đợt nghiệm thu 43/44.

### B. Nên xoá (Không bằng chứng còn cần VÀ không tài liệu nào trỏ vào)
1. `spike_securities_status_check.py`: Thăm dò REST endpoint hạn chế giao dịch ngày 26/09; không có tài liệu hay code nào tham chiếu.
2. `check_refprice_reset.py`: Script kiểm tra giá tham chiếu từ tháng 8/2026, chỉ nhắc trong kế hoạch ban đầu, không có báo cáo số liệu hay caller.
3. `classify_overnight_gaps.py`: Script phân loại 837 bước nhảy giá cũ, chỉ nằm trong kế hoạch tháng 8/2026.
4. `verify_ssi_gaps.py`: Đối chiếu gap nến ngày 15/08/2026 trong prompt Hermes cũ.
5. `backtest_to_db.py`: Khung ghi backtest vào DB từ 30/08/2026, không có caller hay runbook sử dụng.
6. `bingx_account_probe.py`: Script chỉ đọc thăm dò BingX từ Brief 111, hiện tại chưa kết nối đường chạy thật.

### C. Nên giữ nhưng cần tài liệu hoá thêm
1. `check_orders_hygiene.py`: Công cụ quét và báo cáo các mã lệnh lạ trong bảng `orders` (không sửa DB). Rất hữu ích khi rà soát dữ liệu sau phiên; nên thêm vào `DEPLOYMENT.md` §8.
2. `probe_engine_consumer.py`: Công cụ kiểm tra tình trạng NATS JetStream consumer `engine` độc lập với heartbeat. Cần bổ sung vào `DEPLOYMENT.md` phần xử lý sự cố NATS.
3. `probe_bars_5m_completeness.py`: Công cụ đo tính toàn vẹn của nến 5m và phát hiện nến giá 0. Cần đưa vào quy trình rà soát chất lượng dữ liệu.

---

## 5. Brief sai ở đâu / Điểm lệch / Cái gì không kiểm được
- **Số lượng script Nhóm 3:** Brief ước tính 39, thực tế là 40 do `record_fixtures.py` chỉ xuất hiện trong `tests/fixtures/README.md` chứ không nằm trong `tests/**/*.py`.
- **Số dòng bằng chứng:** Khi tài liệu Markdown và prompt được cập nhật, số dòng của một số file tài liệu dịch chuyển nhẹ so với lịch sử commit cũ. Test `test_scripts_convention.py` được thiết kế thông minh: kiểm chứng file bằng chứng tồn tại và thực sự chứa tên script thay vì so sánh cứng số dòng tuyệt đối.
- **GitNexus:** MCP không hoạt động trong CLI turn này; đã sử dụng phân tích tĩnh AST và regex callsite toàn diện.
- **Kiểm thử toàn bộ:** `ruff check .` sạch; `uv run pytest -q` đạt **1824 passed** (vượt chỉ tiêu $\ge 1821$).

---

## Audit của Claude (04/10/2026)

### A.1. Kết luận: ĐẠT. Claude sửa hai con số sai và đối chiếu 8 dòng với phán quyết của đợt 53.

### A.2. Phạm vi và kỷ luật
`git status` đúng ba file: `scripts/README.md` (thêm mục 4), test mới, báo cáo. **Không file nào bị xoá hay
đổi tên** — `git diff --name-status` không có dòng `D` hay `R` nào. Đúng quy tắc 3 của `scripts/README.md`.

### A.3. Năm dòng bằng chứng Claude kiểm ngẫu nhiên — đều thật
Claude đã nói trước trong brief là sẽ làm việc này. Lấy mẫu 5 dòng (seed 159), mở từng đường dẫn tới đúng số
dòng:

| Script | Dẫn chứng | Tồn tại | Dòng đó có tên script |
|---|---|---|---|
| `spike_securities_summary_raw` | research đợt 53:215 | có | có |
| `measure_cross_sectional` | research đợt 121:520 | có | có |
| `spike_ssi_sdk_derivative_account` | `scripts/measure_derivative_contract_volume.py:35` | có | có |
| `probe_account_balance_22h` | research đợt 150:184 và đợt 152:55 | có | có |
| `spike_ssi_sdk_index_stream` | `docs/prompts/PROMPT_EXECUTE_COLLECTOR_INDEX_STREAMING_SPIKE.md:18` | có | có |

Không có bằng chứng bịa trong mẫu.

### A.4. Phá thử của Claude — phần xác thực bằng chứng chạy thật
Claude thêm một dòng khai báo **bịa**: script không tồn tại, dẫn chứng trỏ vào file không tồn tại. Test bắt
**cả hai** lỗi:

```
AssertionError: Khai báo cho script không còn tồn tại: zzz_bia_dot159
AssertionError: zzz_bia_dot159: bằng chứng trỏ vào file không tồn tại: docs/khong-he-ton-tai-abc.md
```

Hash `scripts/README.md` khôi phục trùng `3af04b03d7165854`. Đây là điểm mạnh nhất của đợt: bảng khai báo
**không thể** chứa dẫn chứng ma mà vẫn xanh.

### A.5. Hai con số trong báo cáo sai — Claude sửa
Báo cáo và tin tóm tắt ghi `CÒN CẦN: 13` và `KHÔNG RÕ: 19`. Đếm theo cột của bảng thật: **15 / 8 / 17**, tổng
40 — bảng tự nhất quán, chỉ phần tóm tắt sai. Đã sửa trong báo cáo.

### A.6. Phát hiện quan trọng: đợt 53 đã kiểm kê việc này, và phán quyết cũ bị bỏ qua
Một dòng bằng chứng trong mẫu của A.3 dẫn tới `research/2026-09-18-dot-53-don-rac-va-kiem-dinh-image.md`
§5.1 — mục tên là **"Kiểm kê rác bằng tham chiếu, không bằng cảm giác"**. Đợt 53 đã làm đúng công việc này
và kết luận **28 script là CÔNG CỤ GIỮ CÓ CHỦ Ý**, 5 script CẦN NGƯỜI QUYẾT.

Agent dùng báo cáo đó làm **vị trí dẫn chứng** nhưng không đọc **phán quyết** trong đó. Claude đối chiếu
bằng script:

> **8 trong 17 dòng `KHÔNG RÕ` đã được đợt 53 kết luận giữ có chủ đích:**
> `spike_securities_summary_raw`, `spike_ssi_sdk_account`, `spike_ssi_sdk_equity_10y_history`,
> `spike_ssi_sdk_hnx_upcom_ohlc`, `spike_ssi_sdk_index_lookup`, `spike_ssi_sdk_index_stream`,
> `spike_ssi_sdk_index_summary`, `spike_ssi_sdk_ohlc`.

Nếu ai coi `KHÔNG RÕ` là danh sách để xoá, **8 công cụ đã được quyết định giữ sẽ bị xoá**. Claude:
- đổi 8 dòng đó sang `CÒN CẦN` (dẫn chứng sẵn có chính là báo cáo đợt 53, nên test vẫn xanh);
- thêm một khối cảnh báo ngay dưới tiêu đề mục 4, nêu tên cả 8 và nói rõ **`KHÔNG RÕ` không phải danh sách
  để xoá**.

Sau khi sửa: **23 CÒN CẦN / 8 ĐÃ GHI SỐ ĐO / 9 KHÔNG RÕ**, tổng 40; `test_scripts_convention.py` 3/3 xanh.

Đây cùng lớp lỗi với bài học đã ghi: **đọc lý do đã ghi trước khi đảo một quyết định đã chốt**.

### A.7. Còn lại
9 dòng `KHÔNG RÕ` thật sự chưa ai kết luận, kể cả đợt 53. Đó là danh sách Claude sẽ mang ra hỏi chủ dự án,
không tự xoá.
