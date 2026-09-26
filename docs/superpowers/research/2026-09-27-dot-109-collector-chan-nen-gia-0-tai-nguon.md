# Đợt 109 — Collector chặn nến giá 0 ngay tại nguồn ghi

Base: main `a5eda8c`. Ngày: Chủ nhật 27/09/2026. Người thực thi: Hermes (`f4a037ad-c2f2-4c60-bb00-e58273bb208a`).
Brief: `docs/superpowers/plans/2026-09-27-brief-dot-109-collector-chan-nen-gia-0-tai-nguon.md`.
Audit: Claude. Không có phiên giao dịch hôm nay nên được phép sửa collector; Claude triển khai sau 15:40 thứ Hai 28/09.

## 1. Kết luận ngắn

1. **Luồng realtime** (`trading/collector/main.py::make_stream_message_handler` → `on_stream_message`):
   sau `wd.beat()` (dòng 170), nếu `is_dirty_bar(bar)` (dòng 175) thì phát **WARN một lần cho mỗi (mã, ngày)**
   nêu mã, `ts`, OHLC, rồi `return` — **không** `persist_snapshot`, **không** `latch.offer` (dòng 206),
   nên nến rác không vào `bars` và không bao giờ được publish lên NATS.
   Nhịp tim vẫn đập: nhận được message nghĩa là luồng sống, không im vì một bản ghi rác.
2. **Nhánh intraday của `run_backfill`**: lọc `is_dirty_bar` khỏi `intraday` **trước** `write_bars`
   (dòng 362 → 374); nếu có bar bỏ thì **một WARN cho mỗi mã** trong lượt chạy, nêu số bar bỏ và `ts`
   đầu/cuối; `counts[sym]` đếm số bar **đã ghi** (dòng 376).
3. Luật **chỉ** là `trading.data_quality.is_dirty_bar` — hai file chỉ `import` hàm đó, không chép điều kiện
   `<= 0` ở đâu khác, không thêm điều kiện nào vào SQL.
4. **Không đụng**: `write_daily`, nhánh `daily_only`, `aggregator.py`, `latch.py`, `parser.py`, storage,
   engine, config, `docker-compose.yml`, Task Scheduler.
5. Số liệu: **5 test mới** (3 luồng realtime + 2 backfill) đỏ trước, xanh sau; **3/3 phép phá bắt được**;
   unit **1131 passed** (mốc 1126 + 5), integration **137 passed** (mốc 137), `ruff` All checks passed.
   Diff: 4 file, +211 / −2 dòng.
6. **Cổng GitNexus — có dừng lại thật.** `impact run_backfill` trả **HIGH** (8 mục, direct 3, 2 process)
   ⇒ theo §2 của brief tôi **dừng ngay, không sửa gì**, báo chủ dự án và **chỉ làm tiếp sau khi chủ dự án
   chọn "làm cả hai"**. Đây là quyết định của người, không phải tôi tự vượt cổng.
7. **Nhận lỗi đợt 108.** Mục Task B của báo cáo đợt 108 truy **sai** đường ghi: tôi khẳng định
   `aggregator.py:38` mở bar từ tick đầu tiên. `BarAggregator` **không có caller nào** trong `trading/`
   (chỉ `tests/` và ghi chú trong script) — đó là code chết. Đường ghi thật đúng như Claude đã kiểm:
   `on_stream_message` → `persist_snapshot` (`main.py:132`, ghi DB mỗi snapshot) → `latch.offer` (`main.py:206`)
   → `persist_bars` (`main.py:80`, publish NATS + ghi DB), và đường backfill `run_backfill` (`backfill.py:330+`).
   Phần **kết luận** của đợt 108 (không commit nào tắt nguồn nến 0; đường ghi vẫn sinh được nến 0) vẫn đúng,
   nhưng phần **đường đi** thì sai — tôi đã gắn nhãn sai cho bằng chứng của chính mình.

## 2. Output test đỏ rồi xanh

Đỏ (trước khi sửa mã):

```
$ uv run pytest tests/test_collector_main.py -q -k "nen_rac or nen_sach"
tests\test_collector_main.py:580: AssertionError
E       assert 0 == 3
E        +  where 0 = len([])
FAILED tests/test_collector_main.py::test_stream_handler_bo_nen_rac_khong_ghi_khong_latch_khong_publish
FAILED tests/test_collector_main.py::test_stream_handler_nen_rac_warn_mot_lan_moi_ma_moi_ngay
2 failed, 1 passed, 28 deselected in 1.70s

$ uv run pytest tests/test_backfill.py -q -k "nen_rac"
tests\test_backfill.py:78: AssertionError
E         At index 1 diff: 545 != 550
E         Left contains one more item: 550
FAILED tests/test_backfill.py::test_run_backfill_bo_nen_rac_intraday
1 failed, 1 passed, 19 deselected in 0.66s
```

Hai test "1 passed" ở mỗi lượt là hai ca **âm bản** (nến sạch đi đường cũ; backfill không có nến bẩn thì
không WARN) — chúng phải xanh cả trước khi sửa, vì hành vi sạch không đổi.

Xanh (sau khi sửa mã):

```
$ uv run pytest tests/test_collector_main.py tests/test_backfill.py -q
52 passed in 2.14s
```

Tên 5 test mới:
- `test_stream_handler_bo_nen_rac_khong_ghi_khong_latch_khong_publish`
- `test_stream_handler_nen_rac_warn_mot_lan_moi_ma_moi_ngay`
- `test_stream_handler_nen_sach_ngay_sau_nen_rac_di_duong_cu`
- `test_run_backfill_bo_nen_rac_intraday`
- `test_run_backfill_khong_warn_khi_khong_co_nen_rac`

## 3. Phá thử

`C:\Users\quelam\AppData\Local\hermes\cache\scratch\sabotage_dot109.py` (script hoá: phá → chạy → `cp` khôi
phục → so `sha256`; **không** dùng `git checkout/restore/stash`). Bản sao lưu **ngoài repo**:
`%LOCALAPPDATA%\Temp\backup_dot109_collector_main.py`, `backup_dot109_backfill.py`.

```
=== truoc khi pha: phai XANH ===
baseline: 5 passed, 47 deselected in 0.77s | do: []

=== PHA THU (i): kiem ban SAU persist_snapshot ===
pha-i: 2 failed, 3 passed | do: ['test_stream_handler_bo_nen_rac_khong_ghi_khong_latch_khong_publish',
                                'test_stream_handler_nen_rac_warn_mot_lan_moi_ma_moi_ngay']

=== PHA THU (ii): kiem ban TRUOC wd.beat() ===
pha-ii: 2 failed, 3 passed | do: ['test_stream_handler_bo_nen_rac_khong_ghi_khong_latch_khong_publish',
                                 'test_stream_handler_nen_rac_warn_mot_lan_moi_ma_moi_ngay']

=== PHA THU (iii): bo loc o backfill ===
pha-iii: 1 failed, 4 passed | do: ['test_run_backfill_bo_nen_rac_intraday']

=== sau khi khoi phuc: phai XANH lai ===
sau-khoi-phuc: 5 passed, 47 deselected in 1.06s | do: []

  trading/collector/main.py: KHOP 108870f49c0057f2
  trading/collector/backfill.py: KHOP 96ea2c0f9e40249f
```

Đọc từng phép:
- (i) kiểm bẩn đặt **sau** `persist_snapshot` ⇒ nến rác **đã kịp ghi DB** ⇒ test "không được gọi
  `storage.write_bars`" đỏ (và test chống-báo-trùng đỏ theo, vì mã chạy tiếp vào nhánh sạch). Đúng nghĩa phá luật.
- (ii) kiểm bẩn đặt **trước** `wd.beat()` ⇒ nến rác không đập nhịp tim ⇒ `wd.beat.assert_called_once()` đỏ.
  Đúng nghĩa phá luật "giữ nguyên nhịp tim".
- (iii) bỏ lọc ở backfill ⇒ `write_bars` nhận 3 bar và `counts["VCB"] == 3` ⇒ test đỏ.
- Sau khôi phục: xanh lại đủ 5, hash hai file khớp bản sao lưu.

Chú ý phương pháp: mỗi lệnh `pytest` chỉ dùng **một** `-k` (bài học đợt 107–108); phép phá chỉ được coi là
"bắt được" khi có **tên test đỏ** in ra, không chỉ "exit code khác 0".

## 4. Bước 4 — `stream-health` và cổng go-live có đếm theo khung ATO/ATC không?

**Có, và không dùng `CONTINUOUS_SESSIONS`.** Trả lời thẳng: giả định trong brief ("hãy xác nhận các thước đo
độ phủ dùng đúng định nghĩa đó") **không đúng** với `scripts/stream_health_check.py`.

- `trading/calendar_vn.py:103`: `CONTINUOUS_SESSIONS = [time(9,15)–time(11,30), time(13,0)–time(14,30)]`;
  `:106` `is_continuous_matching` — loại ATO (09:00–09:15) và ATC (14:30–14:45).
- Engine dùng đúng định nghĩa đó: `trading/engine/main.py:107-108, 122` (`sessions=CONTINUOUS_SESSIONS`).
- Collector chặn giao dịch theo đúng định nghĩa đó: `trading/collector/main.py:285`
  (`in_continuous = is_continuous_matching(now, holidays)`).
- **Nhưng** `scripts/stream_health_check.py` tự khai cửa sổ riêng, **gồm cả ATO/ATC**:
  `:287-288` lọc `ts >= '<ngày> 09:00:00+07' AND ts <= '<ngày> 11:35:00+07'`; `:300-301`
  `13:00:00+07` → `15:05:00+07`; chế độ cả ngày `:314-320` với `ts::time >= '09:00:00' AND <= '11:35:00'`
  hoặc `>= '13:00:00' AND <= '15:05:00'`. Mẫu số `expected = slots × syms` (`:332`) lấy `slots =
  count(DISTINCT time_bucket('5m', ts))` và `count(*)` **từ chính các dòng trong bảng `bars`** (`:283`, `:310`).

Hệ quả đo được (chỉ đọc DB thật; `SET TimeZone='Asia/Ho_Chi_Minh'` như script vẫn làm ở `:278`; 3 mã mặc định
HPG/AAA/IJC; cửa sổ 13/08–16/09, đúng 18 ngày có nến bẩn):

| | có nến bẩn | đã lọc nến bẩn |
|---|---|---|
| số bar | 3164 | 2976 |
| kỳ vọng (slots×syms) | 3333 | 3030 |
| **độ phủ** | **0,9493** | **0,9822** |

Từng ngày đều **tăng**, không ngày nào giảm; ví dụ 07/09 0,8910 → 0,9638, 08/09 0,8846 → 0,9565,
và 19/08, 25/08, 26/08, 09/09, 16/09 lên đúng 1,0000. Lý do: một nến bẩn **tự tạo thêm một khung 5 phút**
cho mẫu số (nên `slots` tăng) mà chỉ đóng góp **một** dòng cho tử số, và ở nhiều ngày nến bẩn còn không đủ
để lấp khung đó. Vậy bỏ nến 0 **làm con số độ phủ cao lên**, không phải thấp đi — nhưng **có ảnh hưởng**,
và đây là chỗ cần Claude quyết có nên sửa `stream_health_check.py` cho dùng `CONTINUOUS_SESSIONS` hay không
(tôi **không** sửa, ngoài phạm vi).

Nến bẩn nằm đúng hai khung đó (giờ VN):

```
 gio_vn | so_dong |      khung
--------+---------+-----------------
 09:00  |      43 | ATO 09:00-09:15
 09:05  |      46 | ATO 09:00-09:15
 09:10  |      49 | ATO 09:00-09:15
 14:30  |      41 | ATC 14:30-14:45
 14:35  |      41 | ATC 14:30-14:45
 14:40  |      41 | ATC 14:30-14:45
```

Ghi chú phương pháp: lượt đo đầu tiên của tôi ra **0 dòng** vì phiên `psql` trong container mặc định UTC nên
`ts::time >= '09:00'` không khớp gì (dòng bẩn in ra là `02:00+00` = 09:00 VN). Phải `SET TimeZone` trước khi
so `ts::time`; script thật đã làm đúng việc này ở `stream_health_check.py:278`.

## 5. `gitnexus impact` (trước khi sửa) và `detect-changes`

Chạy **trước** khi sửa (qua CLI, `--repo AI_auto_trading_system`), dán nguyên văn các trường chính:

```
make_stream_message_handler : "impactedCount": 3,  "risk": "LOW",   "summary": {"direct": 1}, "processes_affected": 1
run_backfill               : "impactedCount": 8,  "risk": "HIGH",  "summary": {"direct": 3}, "processes_affected": 2
```

⇒ `run_backfill` **HIGH**: tôi dừng, không sửa gì, báo chủ dự án, chờ quyết định. Chủ dự án chọn "làm cả hai"
(thay đổi chỉ là lọc thêm + WARN + đếm lại, không đổi chữ ký hàm; 3 caller đều nằm trong cùng collector).
Chữ HIGH này được ghi lại ở đây để Claude đối chiếu.

`detect-changes` (`--scope all --repo AI_auto_trading_system`) sau khi sửa:

```
"summary": { "changed_count": 42, "affected_count": 4, "changed_files": 4, "risk_level": "medium" }
```

Kiểm tra toàn cục:

```
uv run pytest -m "not integration" -q   → 1131 passed, 137 deselected in 25.14s   (mốc brief 1126 + 5)
uv run pytest -m integration -q         →  137 passed, 1131 deselected in 34.84s  (mốc brief 137)
uv run ruff check trading tests         → All checks passed!
git diff --stat                         → 4 files changed, 211 insertions(+), 2 deletions(-)
```

Bốn file: `trading/collector/main.py` (+26), `trading/collector/backfill.py` (+19),
`tests/test_collector_main.py` (+120), `tests/test_backfill.py` (+46 / −2).

## 6. Những điều thấy ngoài phạm vi

1. **`aggregator.py` — code chết, và nó là chỗ tôi truy sai ở đợt 108.** `grep -rn "BarAggregator"` chỉ ra
   `trading/collector/aggregator.py` (định nghĩa) cùng các file test/ghi chú; **không** có caller nào trong
   `trading/`. Tôi **không xoá**, không sửa (đúng như brief dặn). Đề xuất: ghi vào danh sách "code chết đã
   xác nhận" để lần sau không ai lại truy nguồn qua nó — và cũng để không ai đọc bài học "thêm guard vào
   aggregator" mà tưởng là có tác dụng.
2. **`bars_daily` có 71.439 dòng bẩn** (2016–2024; **không** có dòng nào 2025–2026): dạng `open = 0` nhưng
   `close` thật (ví dụ LAI 2016-01-03: open 0, close 2030.527), `volume = 0`. Đây là **dạng khác** với 261 nến
   trong `bars` (khác đường sinh: `bars_daily` đến từ backfill lịch sử). Tôi **chỉ đếm và báo**, không đụng
   `write_daily`/`daily_only` như brief dặn; lưu ý NAV có thể phụ thuộc `close` của chính những dòng này.
3. **`stream_health_check.py` không dùng `CONTINUOUS_SESSIONS`** (mục 4) — có thể là chủ ý (đo phủ cả khung
   ATO/ATC) hoặc là lệch định nghĩa; cần Claude quyết. Cửa sổ "cả ngày" `13:00–15:05` còn phủ cả ATC.
4. **Phụ thuộc gián tiếp**: sau khi lọc, các khung 09:05/09:10/14:30/14:35/14:40 của 6 mã đó sẽ **không còn**
   trong `bars` — bất kỳ script đếm theo khung giờ sẽ thấy tổng giảm (ví dụ `scripts/probe_bars_5m_completeness.py`
   đếm `close = 0 OR volume = 0` ở dòng 73 và 237). Đó là hệ quả đúng, không phải lỗi, nhưng nên để trống chỗ này.
5. **Chỗ tôi tự sửa mình trong lúc làm** (ghi lại để Claude soi lại được): kỳ vọng đầu của tôi về `counts` và
   ngưỡng WARN đều dựa trên "số bar kéo về" chứ không phải "số bar đã ghi"; và lượt đo độ phủ đầu tiên sai vì
   thiếu `SET TimeZone` (mục 4). Cả hai đã sửa ở phía **test/phép đo**, không phải bằng cách nới ngưỡng mã.
6. File `.md` chưa theo dõi "Các chiến lược BTCUSDT perpetual 1H …" vẫn còn từ đợt 105/106, không liên quan
   đợt này, tôi không đụng.

Tôi không commit, không push, không build hay restart container, không ghi DB thật.

---

## Ghi chú kiểm chứng của Claude (27/09/2026)

**Đạt.** Claude đã đọc diff:
- Luồng realtime chặn nến bẩn **sau** `wd.beat()` và **trước** `persist_snapshot` và `latch.offer`.
- Cảnh báo WARN chỉ phát một lần cho mỗi cặp (mã, ngày). Tập các mã đã báo được xoá khi sang ngày mới.
- Backfill lọc nến bẩn trước `write_bars`, và `counts` đếm số bar đã ghi thật.
- Luật lọc chỉ nằm ở `is_dirty_bar`.

**Chạy lại độc lập:**
- 1131 unit và 137 integration đều pass, ruff sạch.
- `detect-changes` ra mức medium: 4 file, 4 luồng xử lý.
- Impact HIGH của `run_backfill`: agent đã dừng lại đúng cổng và chỉ làm tiếp khi được đồng ý. Thay đổi trong hàm đó chỉ là một phép lọc trước lệnh ghi.

**Hai điểm ghi nhận, không sửa:**
1. **Backfill có thể báo WARN lặp lại mỗi đêm.** Nếu REST trả nến giá 0 ở cuối chuỗi, `last_bar_ts` không tiến lên, nên lượt sau kéo lại đúng các nến đó và báo WARN lần nữa. Đây là tiếng ồn chứ không làm hỏng dữ liệu. Chỉ xử lý nếu thực tế WARN này xuất hiện.
2. **`stream_health_check.py` đếm cả khung ATO/ATC** (dòng 287–320), không dùng `CONTINUOUS_SESSIONS`. Sau khi xoá 261 dòng nến giá 0, độ phủ lịch sử của các ngày 13/08–16/09 sẽ **tăng** (agent đo được 0,9493 → 0,9822). Lý do là mỗi nến bẩn tự thêm một khung vào mẫu số. Cần biết điều này khi đọc lại số độ phủ cũ. Việc đổi định nghĩa độ phủ là một quyết định riêng, không nằm trong đợt này.
