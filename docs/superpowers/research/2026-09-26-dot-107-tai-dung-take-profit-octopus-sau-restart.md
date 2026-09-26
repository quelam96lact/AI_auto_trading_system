# Đợt 107 — tái dựng take-profit Octopus sau restart

Brief: `docs/superpowers/plans/2026-09-26-brief-dot-107-tai-dung-take-profit-octopus-sau-restart.md` (9.906 ký tự).
HEAD khi bắt đầu: `76b6af3`. Ngày: 2026-09-26. Người thực hiện: Hermes (`f4a037ad-c2f2-4c60-bb00-e58273bb208a`).

Ràng buộc đã giữ: **KHÔNG** commit, **KHÔNG** push, **KHÔNG** bật `real_trading_enabled`, **KHÔNG** sửa config,
**KHÔNG** gọi API đặt lệnh, **KHÔNG** restart engine production (engine vẫn chạy code cũ suốt đợt này),
mọi thao tác trên DB thật đều **chỉ đọc** (`SELECT`), không `TRUNCATE/DROP`.
Không sửa dòng nào của đợt 105/106 (vẫn còn nguyên trạng thái chưa commit).

## 1. Kết luận bước 1 — bar neo A là bar nào

**A = bar có `ts == fill.ts`**, tức *bar đầu tiên `strategy.on_bar` thấy `held > 0`* — không phải "bar sau fill",
không phải "bar cuối trước fill".

Chuỗi bằng chứng (đọc mã, không suy đoán):

| Bằng chứng | Vị trí | Nội dung |
|---|---|---|
| Broker khớp lệnh TRƯỚC | `trading/engine/logic.py:36` | `fills = broker.on_bar(bar)` |
| Strategy nhận bar SAU | `trading/engine/logic.py:44` | `signal = strategy.on_bar(bar, broker)` |
| Fill mang mốc thời gian của chính bar đó | `trading/paper_broker.py:203` | `return [Fill(bar.symbol, signal.side, qty, price, fee, bar.ts, pnl)]` |
| Vị thế đã tăng ngay trong lượt đó | `logic.py:36` → `broker.on_bar` | nên `context.position_qty(sym) > 0` ngay tại bar khớp |

Hệ quả: `strategy.on_bar` ở bar `A` là **lần đầu** thấy `held > 0`, và `_tp` rỗng (sau restart) nên nó rơi vào
nhánh `tp = bar.open + tp_atr_mult * atr` (`trading/strategies/octopus_pullback.py`, nay là dòng 253) với
`bar = A`. Vì vậy A phải được tra bằng **`ts >= fill.ts`** (không phải `>`): nếu bar `A` tồn tại trong DB thì
`ts == fill.ts`; điều kiện `>` sẽ lệch sang bar kế tiếp và cho ATR khác.

**ATR khôi phục được bằng đúng giá trị sống**: `AtrCalculator` là **trung bình TR trên `period` nến cuối**
(deque `maxlen=period`, `trading/indicators.py`) nên ATR tại A chỉ phụ thuộc `period+1 = 15` nến cuối — cửa sổ
`warmup_bars = 201` bar kết thúc tại A tái tạo **chính xác** giá trị, không phải xấp xỉ.

## 2. Những gì đã thay đổi

| File | Thay đổi |
|---|---|
| `trading/strategy.py` | Thêm Protocol `RestoresTakeProfit` (`@runtime_checkable`, dòng 58, đúng **một** phương thức `restore_take_profit` dòng 69) |
| `trading/strategies/octopus_pullback.py` | `_tp_level(anchor_open, atr)` (dòng 213) = **một công thức một chỗ**; `restore_take_profit` (dòng 222); `on_bar` (dòng 253) dùng lại `_tp_level`; thêm `self.atr_period` (dòng 116) |
| `trading/storage/db.py` | `read_last_buy_fill` (dòng 270), `read_anchor_bar` (dòng 284, `ts >= fill_ts`), `read_bars_until` (dòng 301, khuôn `read_last_bars`) |
| `trading/engine/main.py` | Khối tái dựng (dòng 292), cổng `if isinstance(strategy, RestoresTakeProfit)` (dòng 301) — **không dùng `hasattr`** |
| `tests/test_octopus_pullback.py` | +3 test (15 → 18) |
| `tests/test_storage_engine.py` | +4 test (9 → 13) |
| `tests/test_engine_main.py` | +3 test (51 → 54) |

`git diff --stat`: 7 files changed, 403 insertions(+), 3 deletions(-).
Không đổi công thức TP: `_tp_level` giữ nguyên `anchor_open + tp_atr_mult * atr` như code cũ.

## 3. Test đỏ rồi xanh

Đỏ (trước khi có mã, `uv run pytest tests/test_octopus_pullback.py -q -k "restore or neo_lai"`):

```
tests\test_octopus_pullback.py:395: AttributeError
E       AttributeError: 'OctopusPullbackStrategy' object has no attribute 'restore_take_profit'
FAILED tests/test_octopus_pullback.py::test_restore_take_profit_bang_dung_tp_luong_song
FAILED tests/test_octopus_pullback.py::test_restore_take_profit_none_khi_thieu_bar
FAILED tests/test_octopus_pullback.py::test_on_bar_sau_khoi_phuc_khong_neo_lai_tp
3 failed, 15 deselected in 0.39s
```

Xanh:

```
tests/test_octopus_pullback.py            18 passed in 0.32s
tests/test_storage_engine.py  -k "read_last_buy or read_bars_until or read_anchor"    5 passed, 8 deselected
tests/test_engine_main.py     -k "take_profit"                                        3 passed, 51 deselected
```

Test đắt giá nhất là `test_restore_take_profit_bang_dung_tp_luong_song`: nó chạy **cả hai đường** rồi so
`==` tuyệt đối (cố ý không `approx`) — luồng sống (warm-up 201 bar + `on_bar` tại bar cuối) và luồng khôi
phục (chiến lược mới + `restore_take_profit` cùng chuỗi bar). Test `test_on_bar_sau_khoi_phuc_khong_neo_lai_tp`
có **đối chứng**: cùng chuỗi bar, chiến lược KHÔNG khôi phục thì neo lại và bán, chiến lược ĐÃ khôi phục thì
không bán.

Một kỳ vọng của tôi đã SAI và bị chính lượt chạy bắt: `test_read_bars_until...` tôi viết
`[ts[1], ts[2]]` trong khi ghi 5 bar rồi xin 3 bar `<= ts[2]` thì phải ra `[ts[0], ts[1], ts[2]]`
(`assert [datetime...] == [datetime...]` đỏ) — sửa **test**, giữ mã.

## 4. Phá thử (3 phép brief yêu cầu) — cả 3 bắt được

Sao lưu **ra ngoài repo** (`%LOCALAPPDATA%/Temp/backup_dot107_*`), phá, chạy test, khôi phục bằng `cp`,
so `sha256sum` — **không** dùng `git checkout/restore/stash`. Script: `sabotage_dot107.py`.

| # | Phép phá | Test đỏ |
|---|---|---|
| (i) | `read_anchor_bar`: `ts >= fill_ts` → `ts > fill_ts` | `test_engine_restores_octopus_take_profit_after_restart` |
| (ii) | `restore_take_profit`: lấy `close` của A làm neo thay vì `open` | `test_restore_take_profit_bang_dung_tp_luong_song` |
| (iii) | Xóa nhánh `WARN` khi không có BUY (thất bại im lặng) | `test_engine_warns_when_octopus_take_profit_cannot_restore` |

Sau mỗi phép: khôi phục khớp `sha256`, chạy lại xanh. **Thiếu sót của tôi ở lượt phá (i)**: lệnh pytest
truyền hai `-k` nên cái sau đè cái trước, test storage KHÔNG chạy trong lượt đó; tôi đã chạy lại riêng —
`test_read_anchor_bar_la_bar_dau_tien_ts_khong_nho_hon_fill_ts` cũng đỏ (1 failed, 12 deselected), khôi phục
xanh lại (1 passed). Vậy phép phá (i) bị bắt bởi **2** test, không phải 1.

## 5. Chạy khô trên DB thật (chỉ đọc) — IJC và AAA

`dryrun_dot107.py`, chỉ gọi hàm đọc + `restore_take_profit`; không ghi DB, không restart engine.

```
=== IJC ===
  BUY: ts=2026-09-03 09:15:00+07:00  gia=7353.675
  bar neo A: ts=2026-09-03 09:15:00+07:00  open=7350.000
  so bar cua so=201  ATR_A=2119.285714285714
  TP KHOI PHUC = 11588.571428571428
  bar moi nhat: ts=2026-09-25 14:45:00+07:00  open=6720.000  close=6720.000  ATR_now=20.714285714285715
  TP ma code hien tai se neo (open moi nhat + 2*ATR) = 6761.429
  TP khoi phuc (11588.571) vs close moi nhat (6720.000) -> khong kich hoat
  lech so voi TP neo lai: +4827.143
=== AAA ===
  BUY: ts=2026-09-03 09:20:00+07:00  gia=7053.525
  bar neo A: ts=2026-09-03 09:20:00+07:00  open=7050.000
  so bar cua so=201  ATR_A=2024.2857142857142
  TP KHOI PHUC = 11098.571428571428
  bar moi nhat: ts=2026-09-25 14:45:00+07:00  open=7470.000  close=7470.000  ATR_now=20.0
  TP ma code hien tai se neo (open moi nhat + 2*ATR) = 7510.000
  TP khoi phuc (11098.571) vs close moi nhat (7470.000) -> khong kich hoat
  lech so voi TP neo lai: +3588.571
```

Quan sát nguyên văn, không thêm diễn giải:

- Bar neo tra ra **đúng bằng** bar của lệnh BUY (`ts` khớp từng giây) cho cả hai mã.
- Giá fill = `open` của bar neo × **1,0005** đúng cho cả hai mã (7350 → 7353,675; 7050 → 7053,525).
- **Cả IJC lẫn AAA đều KHÔNG kích hoạt** ở thời điểm chạy (TP khôi phục > close mới nhất), tức dự đoán
  "AAA có thể bán ngay" trong brief **không xảy ra** với số đo này.
- Lý do nằm ở ATR: `ATR_A ≈ 2119` (IJC) và `≈ 2024` (AAA) — lớn bất thường so với giá ~7000, trong khi
  `ATR_now ≈ 20,7`. Xem mục 6.
- Nếu không tái dựng, TP mà code hiện tại sẽ neo là 6761 và 7510 — IJC khi đó chỉ cách close 41 điểm (0,6%).

## 6. Những điều thấy ngoài phạm vi brief (không sửa)

1. **`octopus_combo.py` có đúng lỗi này** (brief yêu cầu báo): `self._tp: dict[str, float] = {}` (dòng 84),
   `tp = bar.open + self.tp_atr_mult * atr` (dòng 175), không có `restore_take_profit`. Chưa sửa.
2. **`bars` của IJC có bar OHLC = 0 trong DB thật** — quan sát trực tiếp khi soi ATR:

   ```
   2026-08-28 14:30:00+07:00  o=0.0 h=0.0 l=0.0 c=0.0  TR=7360.0
   2026-08-28 14:35:00+07:00  o=0.0 h=0.0 l=0.0 c=0.0  TR=0.0
   2026-08-28 14:40:00+07:00  o=0.0 h=0.0 l=0.0 c=0.0  TR=0.0
   2026-08-28 14:45:00+07:00  o=7410.0 h=7410.0 l=7410.0 c=7410.0  TR=7410.0
   2026-09-03 09:00:00+07:00  o=0.0 h=0.0 l=0.0 c=0.0  TR=7410.0
   2026-09-03 09:05:00+07:00  o=0.0 h=0.0 l=0.0 c=0.0  TR=0.0
   2026-09-03 09:10:00+07:00  o=0.0 h=0.0 l=0.0 c=0.0  TR=0.0
   ```

   Các TR giả 7360/7410 này **là nguyên nhân** ATR_A ≈ 2119 → TP khôi phục 11588 (IJC) / 11098 (AAA).
   Nói cách khác: số khôi phục là **trung thành với luồng sống** (luồng sống cũng dùng đúng các TR đó),
   nhưng **giá trị TP dựa trên dữ liệu bẩn** nên thực tế vô hiệu (≈ +58%/+57% so với giá vốn).
   Tái dựng đúng mà đầu vào bẩn thì vẫn ra TP vô nghĩa — cần một đợt riêng để xử lý bar 0 trong `bars`.
3. **Brief yêu cầu alert INFO gồm "mã, neo, ATR, TP"** — tôi ghi `symbol`, `anchor`, `anchor_open`, `tp`,
   **thiếu ATR**: Protocol do chính brief chốt "đúng một phương thức" trả về `float | None`, nên engine không
   có ATR để in, và tôi không muốn mở thêm API chỉ để log (ATR suy ra được: `(tp − anchor_open) / tp_atr_mult`).
   Claude quyết có cần thêm hay không.
4. **"Fake storage" trong brief §2 vs thực tế**: repo **không có** lớp fake storage cho engine
   (`tests/test_engine_main.py` không có `class FakeStorage`); khuôn RESTORE-1 hiện có dùng `Storage` thật
   trên `trading_test`. Tôi theo khuôn đang có, nên 7 test mới của tôi là `integration` (phải có
   `docker compose --profile test up -d nats-test`).
5. `trading/strategy.py` (Protocol mới) **không xuất hiện** trong `changed_symbols` của
   `gitnexus_detect_changes` — chỉ 3 file .py được liệt kê; index GitNexus có khoảng trống với class mới.
6. Log `libpq`/`date_trunc` trong lượt chạy integration không xuất hiện lần này (suite xanh 100%).

## 7. Cổng GitNexus và kiểm tra toàn cục

`gitnexus_impact` chạy **TRƯỚC khi sửa** (§4 brief): `OctopusPullbackStrategy` = 25 mục, direct 9,
**risk MEDIUM**, 0 process → không HIGH/CRITICAL, đi tiếp được. `on_bar` cần `target_uid` (ambiguous), đã lấy.

`gitnexus_detect_changes` sau khi sửa:
`{"changed_count": 30, "affected_count": 5, "changed_files": 7, "risk_level": "medium"}`;
process bị ảnh hưởng nêu tên `run` (step 2) trong `proc_60_main` (Main → _get_pool) và
`proc_69_idle_maintenance`; file có symbol đổi: `trading/engine/main.py`, `trading/storage/db.py`,
`trading/strategies/octopus_pullback.py` (change_type toàn bộ là `touched`).

Test + lint toàn cục:

```
uv run pytest -m "not integration" -q   ->  1123 passed, 134 deselected in 23.58s   (mốc brief 1120 + 3 test mới)
uv run pytest -m integration     -q     ->   134 passed, 1123 deselected in 38.20s   (+7 test mới)
uv run ruff check trading tests         ->  All checks passed!
```

Trong lượt này ruff ban đầu báo `1 error` — `RUF059 Unpacked variable msg is never used`
(`tests/test_engine_main.py:1886`) do test tôi viết; đã sửa thành `_msg` rồi mới xanh.

## 8. Việc còn lại / chưa làm

- Chưa gửi được báo cáo này cho Lead qua cầu 1devtool (mọi lần `link send` trước đó trả `quarantined`;
  xem mục "Cổng" ở phần báo user).
- `octopus_combo.py` chưa được tái dựng (ngoài phạm vi brief).
- Bar OHLC = 0 trong `bars` chưa xử lý (ngoài phạm vi brief) — nhưng nó làm TP khôi phục vô hiệu.
- ATR không có trong dòng INFO (mục 6.3) — chờ Claude quyết.
- Đợt 105 và đợt 106 vẫn chưa commit (báo cáo của hai đợt đó cũng chưa gửi được Lead).

---

## Ghi chú kiểm chứng của Claude (26/09/2026)

**Mã đúng như brief.** Tôi đã đọc toàn bộ diff:
- `_tp_level` là chỗ duy nhất tính TP.
- Engine chỉ gọi khôi phục khi chiến lược thoả `isinstance(RestoresTakeProfit)`.
- Ba nhánh thất bại đều phát WARN, không nhánh nào im lặng.
- Test tương đương so bằng `==` tuyệt đối.

Kết luận "bar neo A = bar của chính lệnh fill" có trích dẫn đúng: `logic.py:36` nạp broker trước khi `logic.py:44` gọi strategy.

Claude chạy lại độc lập:
- `-m "not integration"`: 1123 passed.
- `-m integration`: 134 passed.
- ruff sạch.
- `gitnexus detect-changes` qua CLI (MCP không kết nối được): medium, 5 luồng. Các symbol bị tính là "chạm" chỉ vì khối mới chèn vào `run()` đẩy dòng của các hàm lồng phía sau; nội dung các hàm đó không đổi.

**Việc bỏ ATR khỏi dòng INFO được chấp nhận:** nếu cần thì tính lại được bằng `ATR = (tp − anchor_open) / tp_atr_mult`.

### Phát hiện quan trọng nhất: đầu vào bẩn, không phải lỗi mã

Bảng `bars` có **261 nến giá 0** trên 6 mã, từ 13/08 đến 16/09. Tất cả rơi vào 09:00–09:10 (ATO) hoặc 14:30–14:40 (ATC).
- Từ 17/09 không còn nến giá 0 mới, và cũng không còn nến ATO. Nguồn sinh nến 0 đã tắt, nhưng các dòng cũ vẫn nằm trong DB.
- Engine sống **không** gọi `is_dirty_bar`. Chỉ các engine backtest có gọi.

Hệ quả:
- Khôi phục TP cho IJC/AAA (bar neo 03/09) đi qua các nến 0, nên ATR bị thổi phồng khoảng 100 lần. TP ra 11.588 và 11.098, tức **+58% so với giá vốn**: thực tế là không có TP.
- Lúc 03/09, luồng sống rất có thể cũng đã nhận chính các nến này. Nếu vậy, TP sống khi đó cũng bẩn y như vậy, và "tái dựng đúng" nghĩa là tái dựng đúng một con số rác.

**Triển khai vẫn có lợi:** TP khôi phục cao quá mức còn hơn TP bị neo xuống dưới giá vốn (hành vi cũ: 6.761 cho IJC, dưới giá mua 7.353). Nhưng lỗi gốc vẫn còn, và là việc của đợt sau:
- engine phải bỏ nến bẩn trước khi đưa cho strategy;
- dọn 261 dòng nến 0 sau khi đã sao lưu.

`octopus_combo.py` có cùng lỗi `_tp`, nhưng chiến lược này không chạy thật. Chỉ ghi nhận, không sửa.
