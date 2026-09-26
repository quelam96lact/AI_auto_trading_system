# Đợt 108 — Engine bỏ nến bẩn, và chuẩn bị dọn 261 nến giá 0 trong `bars`

Base: main `9d841d2`. Ngày: 2026-09-26. Người thực thi: Hermes (`f4a037ad-c2f2-4c60-bb00-e58273bb208a`).
Brief: `docs/superpowers/plans/2026-09-26-brief-dot-108-engine-bo-nen-ban-va-don-261-nen-gia-0.md`.

Ràng buộc đã giữ: không commit, không push, không build/restart container, **không chạy DELETE**,
không ghi DB thật (mọi truy vấn trên DB thật đều là `SELECT`/`\copy ... TO STDOUT`),
không đụng collector / `trailing_stop.py` / `paper_broker.py` / `real_orders.py` / `strategies/*` /
config / `docker-compose.yml` / Task Scheduler. Không sửa `storage` (chỉ thêm test dùng `Storage` thật
trên `trading_test`).

## 1. Kết luận ngắn

Task A xong: luật `is_dirty_bar` (một nguồn sự thật ở `trading/data_quality.py:33`) nay được áp ở **cả ba**
đường đưa bar vào engine thật — bar sống (`process_bar`), warm-up, và cửa sổ tái dựng TP — cộng thêm một
nhánh WARN mới khi **bar neo `A` là nến rác**. Đo trên DB thật cho thấy đây đúng là lỗi đã làm TP vô hiệu ở
đợt 107: ATR_A của IJC **2119,29 → 24,29** (bỏ 22 nến rác), của AAA **2024,29 → 22,14** (bỏ 25 nến rác).

**Cảnh báo phải nói trước khi triển khai (brief §3 yêu cầu):** sau khi lọc, TP khôi phục của **AAA =
7.094,29**, trong khi giá đóng cửa gần nhất là **7.470** ⇒ cờ **"SẼ BÁN NGAY KHI TRIỂN KHAI"** đã bật
(đây là bán LÃI: giá vốn 7.053,525, TP 7.094,286 ≈ +0,58%). IJC thì không kích hoạt (TP 7.398,57 > 6.720).
Đây là số của bước 4, dán nguyên văn ở mục 4.

Task B: **không có commit nào trong repo tắt nguồn sinh nến 0** — đã tìm bằng `git log -S` cho mọi mẫu
lọc giá/khối lượng và đọc toàn bộ commit chạm collector từ 01/08 đến 26/09. Nến 0 đến từ luồng tick SSI
(`Close`/`Volume` = 0) đi qua 4 tầng ghi mà **không tầng nào kiểm tra giá trị**. Đường ghi hiện tại **vẫn
còn** khả năng sinh bar giá 0 (chi tiết ở mục 5). Đây là lý do Task A là cần thiết chứ không thừa.

Task C: đã sao lưu **261 dòng** ra `D:\My_Vault_Obsidian\Project\_backups\bars_zero_ohlc_20260926.csv`
(10.745 bytes) và viết (KHÔNG chạy) `delete_bars_zero_ohlc_20260926.sql` cùng thư mục.

## 2. Test đỏ rồi xanh

Đỏ (viết test trước, chưa có mã — `uv run pytest tests/test_engine_logic.py -q -k "nen_rac or nen_sach"`):

```
    fills = process_bar(
        bar_at(6, 20), broker, strategy, risk, trailing_stop, marks, day_state
    )
>   assert [f.side for f in fills] == ["BUY"]
E   AssertionError: assert [] == ['BUY']
FAILED tests/test_engine_logic.py::test_process_bar_bo_nen_rac_khong_cham_broker_marks_hay_strategy
FAILED tests/test_engine_logic.py::test_nen_rac_warn_mot_lan_moi_ma_moi_ngay
FAILED tests/test_engine_logic.py::test_nen_sach_ngay_sau_nen_rac_van_xu_ly_binh_thuong
3 failed, 13 deselected in 0.58s
```

Ba test đó đỏ đúng vì lý do cần sửa: nến 0 lọt vào broker nên lệnh chờ khớp ở giá 0 (vị thế 50000 thay vì 0),
`marks["VCB"]` bị kéo về 0, và lệnh chờ bị "tiêu" ở nến rác nên nến sạch sau đó không khớp được gì.

Xanh:

```
uv run pytest tests/test_engine_logic.py -q                          -> 16 passed in 0.23s   (13 cũ + 3 mới)
uv run pytest tests/test_engine_main.py -q -k "nen_rac or bar_neo"   ->  3 passed, 54 deselected  (integration)
uv run pytest -m "not integration" -q                                -> 1126 passed, 137 deselected in 24.00s
uv run pytest -m integration      -q                                 ->  137 passed, 1126 deselected in 38.14s
uv run ruff check trading tests                                      -> All checks passed!
```

(mốc brief: 1123 unit / 134 integration ⇒ +3 unit +3 integration, đúng bằng số test tôi thêm.)

Hai kỳ vọng của tôi đã SAI và bị chính lượt chạy bắt (sửa test, giữ mã):

1. `test_nen_sach_ngay_sau_nen_rac_van_xu_ly_binh_thuong`: tôi viết `broker.position_qty("VCB") == 100`
   nhưng RiskManager định cỡ lệnh theo vốn ⇒ **50000**. Sửa thành so với `fills[0].qty`.
2. `test_engine_tp_khoi_phuc_bo_nen_rac_trong_cua_so`: tôi lọc alert theo chuỗi `"take-profit"`, nhưng alert
   mới "khoi phuc take-profit … bo N bar rac trong cua so ATR" cũng chứa chuỗi đó ⇒ bắt nhầm alert và
   `KeyError: 'tp'`. Sửa thành `"tai dung take-profit"`.

## 3. Phá thử (3 phép brief yêu cầu)

Sao lưu **ra ngoài repo** (`%LOCALAPPDATA%/Temp/backup_dot108_logic.py`, `backup_dot108_engine_main.py`),
phá, chạy test, khôi phục bằng `cp`, so `sha256`. **Không** dùng `git checkout/restore/stash`.
Script: `sabotage_dot108.py` (mỗi lượt pytest chỉ một `-k` — bài học đợt 107).

```
baseline (truoc khi pha):        9 passed, 64 deselected

(i) kiem ban SAU broker.on_bar:  3 failed
    test_process_bar_bo_nen_rac_khong_cham_broker_marks_hay_strategy
    test_nen_rac_warn_mot_lan_moi_ma_moi_ngay
    test_nen_sach_ngay_sau_nen_rac_van_xu_ly_binh_thuong
(ii) bo loc cua so khoi phuc TP: 1 failed
    test_engine_tp_khoi_phuc_bo_nen_rac_trong_cua_so
(iii) WARN o MOI bar ban:        1 failed
    test_nen_rac_warn_mot_lan_moi_ma_moi_ngay

sau khi khoi phuc:               9 passed, 64 deselected
hash: trading/engine/logic.py      KHOP 81c4775c9dabfe36
      trading/engine/main.py       KHOP af94e149703efa3a
```

**Phép phá (ii) lần đầu KHÔNG bị bắt** — và đây là lỗi của test tôi viết, không phải của mã: tôi đặt hai nến
rác ở vị trí 100 và 150 trong cửa sổ 201 bar, nhưng ATR là trung bình **14 TR cuối**, nên hai nến rác kia
không ảnh hưởng gì tới ATR tại bar neo ⇒ ATR lọc và không lọc **bằng nhau** ⇒ test xanh dù lọc bị bỏ. Sửa
bằng cách đặt nến rác **sát bar neo** (`n-5`, `n-3`, tức nằm trong 14 TR cuối) thì phép phá bị bắt ngay.
Ghi lại vì đây đúng là loại "test không phân biệt được hai cách hiểu" mà các đợt trước đã gặp.

## 4. Chạy khô (chỉ đọc DB thật) — IJC và AAA

`dryrun_dot108.py` (ngoài repo), chỉ `SELECT` + `restore_take_profit`; không ghi DB, không restart engine.

```
=== IJC ===
  BUY: ts=2026-09-03 09:15:00+07:00  gia=7353.675
  bar neo A: ts=2026-09-03 09:15:00+07:00  open=7350.000
  cua so: 201 bar, BO 22 bar rac
  ATR_A (chuoi da loc) = 24.285714285714285
  ATR_A (khong loc)    = 2119.285714285714   <- so sanh
  TP KHOI PHUC = 7398.571428571428
  bar moi nhat: ts=2026-09-25 14:45:00+07:00  close=6720.000  (cua so nay bo 0 bar rac)
  TP khoi phuc (7398.571) vs close moi nhat (6720.000) -> khong kich hoat
  TP ma code cu (neo lai, da loc) se dung = 6761.429
=== AAA ===
  BUY: ts=2026-09-03 09:20:00+07:00  gia=7053.525
  bar neo A: ts=2026-09-03 09:20:00+07:00  open=7050.000
  cua so: 201 bar, BO 25 bar rac
  ATR_A (chuoi da loc) = 22.142857142857142
  ATR_A (khong loc)    = 2024.2857142857142   <- so sanh
  TP KHOI PHUC = 7094.285714285715
  bar moi nhat: ts=2026-09-25 14:45:00+07:00  close=7470.000  (cua so nay bo 0 bar rac)
  TP khoi phuc (7094.286) vs close moi nhat (7470.000) -> SE BAN NGAY KHI TRIEN KHAI
  TP ma code cu (neo lai, da loc) se dung = 7510.000
```

Bar neo tra ra đúng bằng bar của lệnh BUY cho cả hai mã, giá fill = `open` × 1,0005 (7350 → 7353,675;
7050 → 7053,525) — không đổi so với đợt 107. **Cờ "SẼ BÁN NGAY" đã bật với AAA** (xem mục 1).

## 5. Task B — nến giá 0 sinh từ đâu

**Dữ liệu (SELECT trên `bars`, chỉ đọc):** 261 dòng, 6 mã, `source='ssi'`, `volume=0` toàn bộ, giờ (UTC)
`02:00/02:05/02:10` và `07:30/07:35/07:40` = **09:00/09:05/09:10 (ATO)** và **14:30/14:35/14:40 (ATC)** giờ VN.
Phân bố: AAA 76, IJC 73, HII 67, HPG 39, TCB 3, VCB 3; 13/08 → 16/09.

**Đường ghi (không tầng nào kiểm tra giá trị):**

| Tầng | Dòng | Việc |
|---|---|---|
| `trading/collector/parser.py` | `35-36`, `40` | `price = ci_get(content, "Close")`, `volume = ci_get(content, "Volume")` → `Tick(..., float(price), int(float(volume or 0)), ts)` — **không** kiểm `price > 0` |
| `trading/collector/aggregator.py` | `38`, `52-53` | mở bar từ tick ĐẦU của khung (`_OpenBar(bucket, t.price, …)`), `_freeze` đổ thẳng ra `Bar` |
| `trading/collector/latch.py` | `35-43` | chỉ quyết định khung nào đã CHỐT; không soi giá trị |
| `trading/storage/db.py` | `110-113`, `122-123` | `_write` chỉ bỏ qua danh sách rỗng; **không** validate OHLC |

**Commit nào tắt nguồn?** Không có. Bằng chứng:
`git log --oneline -S "price <= 0" -- trading/` → rỗng; `-S "volume <= 0"` → rỗng;
`grep -n "price <= 0|price > 0|volume <= 0|volume > 0"` trong `parser.py`/`feed.py` → rỗng.
Toàn bộ commit chạm `trading/collector` từ 01/08→26/09 đã đọc: nhóm 10-14/09 lo BarLatch/lag/backfill,
`4b7063f` (18/09, dot52) chỉ thêm log bền + đổi định dạng (đã xem `git show` từng dòng), `e830d64`/`e9d38d9`
(19/09) lo logger, `f191f01` (14/09) event study, `32fbf80` (25/09) số dư tài khoản. Không commit nào chạm
đường ghi bar để lọc giá 0. Nghĩa là việc nến 0 ngừng xuất hiện từ 17/09 **không có nguyên nhân trong mã
repo này** — giả thuyết hợp lý nhất là phía luồng SSI thôi phát các bản ghi ATO/ATC giá 0, nhưng tôi
**không chứng minh được** điều đó bằng mã, nên chỉ nêu ra chứ không kết luận.

**Đường ghi hiện tại còn sinh được bar giá 0 không? CÓ.** Vì cả 4 tầng đều không kiểm giá trị, một tick
`Close=0` (ATO/ATC, mã thanh khoản thấp, hoặc dữ liệu lỗi phía SSI) sẽ lại đi thẳng vào `bars` như cũ.
Đây chính là lý do phải có lọc ở phía engine (Task A) chứ không thể trông vào dữ liệu sạch.

## 6. Task C — chuẩn bị dọn dữ liệu

1. **Sao lưu** (ngoài repo, KHÔNG dùng `pg_dump -t`):

```
docker exec -i ai_auto_trading_system-postgres-1 sh -c \
  'PGPASSWORD=$POSTGRES_PASSWORD psql -U $POSTGRES_USER -d $POSTGRES_DB -c \
   "\copy (SELECT * FROM bars WHERE open<=0 OR high<=0 OR low<=0 OR close<=0 ORDER BY symbol, ts) TO STDOUT WITH CSV HEADER"' \
  > D:\My_Vault_Obsidian\Project\_backups\bars_zero_ohlc_20260926.csv
```

Kết quả: file **10.745 bytes**, **262 dòng = 1 tiêu đề + 261 dòng dữ liệu** (đúng bằng 261 của brief).
Dòng đầu: `symbol,ts,open,high,low,close,volume,source` / `AAA,2026-08-13 02:00:00+00,0,0,0,0,0,ssi`;
dòng cuối: `VCB,2026-08-13 02:10:00+00,0,0,0,0,0,ssi`.

2. **Script SQL** (đã viết, CHƯA chạy): `D:\My_Vault_Obsidian\Project\_backups\delete_bars_zero_ohlc_20260926.sql`
   — một transaction, `\set ON_ERROR_STOP on`, `DO $$ … $$`: đếm trước, `RAISE EXCEPTION` nếu ≠ **261**;
   `DELETE` đúng điều kiện của bước 1; `GET DIAGNOSTICS` bắt số dòng xoá, phải = 261; đếm lại phải = 0 nếu
   không thì `RAISE EXCEPTION` (⇒ ROLLBACK); cuối cùng `COMMIT` + một `SELECT count(*)` kiểm lại.

3. **Các SELECT kiểm (chỉ đọc, đã chạy):**

```
tong_dong_bam | so_ma |  tu_ngay   |  den_ngay
           261 |     6 | 2026-08-13 | 2026-09-16

 symbol | so_dong |     tu     |    den     |                 gio
 AAA    |      76 | 2026-08-13 | 2026-09-16 | 02:00,02:05,02:10,07:30,07:35,07:40
 IJC    |      73 | 2026-08-13 | 2026-09-16 | 02:00,02:05,02:10,07:30,07:35,07:40
 HII    |      67 | 2026-08-13 | 2026-09-04 | 02:00,02:05,02:10,07:30,07:35,07:40
 HPG    |      39 | 2026-08-13 | 2026-09-16 | 02:00,02:05,02:10,07:30,07:35,07:40
 TCB    |       3 | 2026-08-13 | 2026-08-13 | 02:00,02:05,02:10
 VCB    |       3 | 2026-08-13 | 2026-08-13 | 02:00,02:05,02:10

source | volume |  n        -> ssi | 0 | 261

dong_ban_bars_daily  ->  71439
```

   - **`bars_daily` có 71.439 dòng bẩn** — không phải "một vài". Xem mục 8 vì sao tôi KHÔNG đụng và không
     coi đó là cùng một lỗi.
   - Sau khi xoá, các khung 09:05/09:10/14:30/14:35/14:40 **biến mất hoàn toàn** khỏi `bars` (hiện chỉ còn
     khung 09:00 với 30 nến, tất cả giá dương, từ 13/08) — đúng như brief mô tả "từ 17/09 không còn nến ATO".

4. **Bảng/script khác đọc `bars` (grep `FROM bars`)**: `trading/engine/main.py` (warm-up + cửa sổ TP — nay đã
   tự lọc), `trading/storage/db.py` (`read_bars`, `read_last_bars`, `read_bars_until`, `read_anchor_bar`), và
   các script đo/kiểm: `scripts/check_real_order_readiness.py:143`, `scripts/compare_timeframe_mismatch.py:57,148`,
   `scripts/measure_session_stream_metrics.py:161`, `scripts/probe_bars_5m_completeness.py:51,70,73,77,189,202,222,237`
   (script này **đếm sẵn** `close = 0 OR volume = 0`), `scripts/backfill_spike_data_to_db.py:83,101`,
   `scripts/heartbeat_check.py:253`, `scripts/measure_*` (chọn vũ trụ mã bằng `SELECT DISTINCT symbol FROM bars`).
   **Không** có chỗ nào đọc `bars` theo khung ATO/ATC để ra quyết định: `trading/calendar_vn.py:107`
   (`is_continuous_session`) đã **loại trừ** ATO/ATC khỏi phiên khớp lệnh liên tục, `trading/resample.py:58`
   chỉ ghi chú bar ATC lệch 14:45. Việc xoá 261 dòng sẽ **đổi số đếm** của các script đo/probe, không đổi
   hành vi engine ngoài việc làm ATR/EMA sạch lên.

## 7. Cổng GitNexus

Chạy TRƯỚC khi sửa (CLI qua wrapper, `npx` chết vì mạng như các đợt trước):

```
process_bar : impactedCount=3, risk=LOW, direct=1, processes_affected=1, modules_affected=2
              affected_processes: main (trading/engine/main.py)
run         : target_uid=Function:trading/engine/main.py:run -> impactedCount=4, risk=LOW,
              direct=1, processes_affected=1, modules_affected=1, process: main
```

Cả hai đều LOW ⇒ không có HIGH/CRITICAL ⇒ đi tiếp.

Sau khi sửa, `detect_changes`:

```
summary: {"changed_count": 32, "affected_count": 6, "changed_files": 4, "risk_level": "high"}
files:  trading/engine/logic.py, trading/engine/main.py, tests/test_engine_logic.py
processes: Main → _get_pool; Idle_maintenance → _get_pool; Process_bar → _day_index; Main → Restore
```

Nói thẳng: `risk_level` của `detect_changes` là **high** (khác với cổng `impact` trước khi sửa là LOW).
Nó phản ánh bán kính ảnh hưởng ở tầng process (32 symbol đổi, 6 process bị chạm), không phải một cảnh báo
tôi đã bỏ qua: brief yêu cầu dừng khi `impact` trả HIGH/CRITICAL, và `impact` trả LOW cho cả hai hàm.

## 8. Những điều thấy ngoài phạm vi (không sửa)

1. **`bars_daily` có 71.439 dòng OHLC ≤ 0** (2016: 29.662; 2017: 9.919; 2018: 1.715; 2019: 47; 2020: 10.634;
   2021: 11.139; 2022: 6.774; 2023: 1.525; 2024: 24 — **không có dòng nào từ 2025 trở đi**). Mẫu cho thấy
   dạng dòng là `open = 0` nhưng `close` là giá thật (ví dụ `LAI 2016-01-03 open=0 close=2030.527 volume=0`),
   tức khác hẳn "nến 0" của `bars` (cả 4 giá = 0). `write_daily` chỉ được gọi từ `trading/collector/backfill.py:349,360`
   ⇒ đây là dạng dữ liệu của đường BACKFILL lịch sử, không phải rác từ luồng sống. Tôi chỉ đếm và báo, không
   kết luận là lỗi, và không đụng.
2. **Bar neo `A` là nến rác ⇒ engine WARN rồi KHÔNG khôi phục TP, nhưng luồng sống sau đó vẫn NEO LẠI TP**
   theo giá mở cửa bar đầu tiên (hành vi đợt 107 còn lại). Đây là lỗ hổng còn hở: nếu bar fill của một vị thế
   là nến rác thì TP vẫn bị neo lại sai. Brief 108 chỉ yêu cầu WARN + không khôi phục nên tôi giữ đúng phạm vi.
3. **`parser.py:36`**: `volume or 0` biến volume thiếu thành 0 một cách im lặng, còn `price` thì lấy nguyên —
   nên một tick `Close=0` đi qua mà không có bất kỳ cảnh báo nào ở phía collector.
4. `scripts/probe_bars_5m_completeness.py` đếm `close = 0 OR volume = 0` trên `bars`; sau khi Claude xoá 261
   dòng, các con số của script này sẽ đổi — không phải lỗi, chỉ để không ai ngạc nhiên.
5. **Vị trí đặt kiểm bẩn trong `process_bar` lệch một nhịp so với câu chữ của brief** ("ngay đầu hàm"): tôi
   đặt nó **ngay sau** khối reset ngày (`day_state["day"] != today`) chứ không phải trước khối đó, vì WARN
   "một lần mỗi mã mỗi ngày" phải dùng chung `day_state` với khuôn `stop_blocked_alerted` — nếu đặt trước
   khối reset thì phải chép lại định nghĩa "sang ngày mới" ở nhánh nến rác (định nghĩa thứ hai của cùng một
   luật). Về hiệu ứng thì không đổi: nến rác vẫn bị chặn TRƯỚC `broker.on_bar`, trước `marks`, trước
   `strategy`; khối reset chỉ ghi `day_state` (không có tác dụng phụ nào khác), và nến rác không thể sinh
   fill nên mốc `start_realized` vẫn đúng.
6. `git status` chỉ có 4 file tôi sửa (2 mã + 2 test); file `.md` chưa theo dõi "Các chiến lược BTCUSDT
   perpetual 1H …" vẫn còn nguyên từ đợt 105, không liên quan đợt này.

Tôi không commit, không push, không build hay restart container, không chạy DELETE hay ghi DB thật.

---

## Ghi chú kiểm chứng của Claude (27/09/2026)

**Đạt.** Claude đã đọc diff của `logic.py` và `main.py`:
- Nến bẩn bị chặn ở đầu `process_bar`, trước broker, trước `marks` và trước strategy.
- Mỗi mã chỉ có một WARN mỗi ngày; cờ đánh dấu reset trong cùng khối reset ngày với `stop_blocked_alerted`.
- Warm-up và cửa sổ khôi phục TP đều lọc bằng `is_dirty_bar`.
- Bar neo bẩn → WARN, không khôi phục.
- Không có định nghĩa thứ hai của luật trong SQL.

**Chạy lại độc lập:**
- 1126 unit và 137 integration pass; ruff sạch.
- File sao lưu có 262 dòng, tức 1 dòng tiêu đề và 261 dòng dữ liệu.
- Script DELETE chạy trong một transaction, dừng nếu số dòng khác 261 ở trước, trong hoặc sau khi xoá.

**TP khớp số học tay:**
- AAA: 7.050 + 2 × 22,14 = 7.094,28.
- IJC: 7.350 + 2 × 24,29 = 7.398,58.

**GitNexus detect-changes: HIGH.** Lý do là `process_bar` nằm trên đường nóng mà mọi bar đều đi qua. Mức HIGH đúng với bản chất thay đổi và là có chủ ý. Với bar sạch, hành vi không đổi: toàn bộ test cũ của `process_bar` vẫn xanh.

**Cờ triển khai AAA:** TP khôi phục 7.094 thấp hơn giá gần nhất 7.470. Nếu AAA **chưa** bị stop bán trong phiên 28/09, engine sẽ bán AAA ở bar đầu tiên sau khi triển khai. Đó là bán lãi theo đúng luật chiến lược (+0,58% so với giá vốn). Theo brief 104, AAA đang dưới trailing stop khoảng 7.860, nên nhiều khả năng đã bị bán trong phiên 28/09, trước lúc triển khai. Claude đã báo chủ dự án trước khi triển khai.

**Task B:** không có commit nào tắt nguồn sinh nến 0. Đường ghi hiện tại vẫn có thể sinh nến giá 0, nên cổng lọc ở engine là cần thiết. Nguyên nhân nến 0 ngừng xuất hiện từ 17/09 chưa được chứng minh.

**`bars_daily` có 71.439 dòng bẩn (2016–2024):** đây là dạng khác (open = 0 nhưng close thật), đến từ đường backfill. Các phép đo trên `bars_daily` đã lọc bằng `is_dirty_bar` hoặc bằng danh sách mã loại trừ. Không xử lý trong đợt này.
