# NHIỆM VỤ: Chiến lược "Octopus Pullback" (EMA + MACD) trên bar ngày, lọc thanh khoản ≥ 2 tỷ

Repo: `D:\My_Vault_Obsidian\Project\AI_auto_trading_system`, nhánh `feature/data-layer`, base `fbab5c3`.

## Nguồn và những gì nguồn KHÔNG có

Nguồn: https://www.tradingview.com/script/unKw2grX-The-Octopus-Pullback-Long-Entry-EMA-MACD/

Đây là **indicator**, không phải strategy — trang chỉ có mô tả định tính, **không công bố
Pine Script, không có tham số cụ thể, không có stop loss**. Vì vậy mọi con số dưới đây là
**lựa chọn có chủ ý của người lập kế hoạch**, không phải trích từ nguồn. Đừng tự đổi.

**Va chạm đã biết, chủ dự án đã quyết cách xử lý:** bản gốc chốt lời 0,2% / 0,5% / 1,0%.
Phí khứ hồi VN ~0,3–0,4% và T+2,5 không cho bán trước ~3 phiên, nên mức TP đó là bất khả
thi trên TTCK VN. Quyết định: **giữ nguyên luật VÀO lệnh, thay luật RA lệnh bằng ATR**.

## Luật vào lệnh — chỉ triển khai "Strong Long"

Mô tả gốc có 3 mức tín hiệu. Chỉ **Strong Long** là lệnh mua; "Medium Long" và
"Early Alert" là cảnh báo, **ngoài phạm vi** — đừng làm, để tránh nhân biến thể trước khi
biết có biên lợi thế hay không.

Strong Long = đồng thời cả ba:
1. **Xu hướng tăng:** `close > EMA(200)`.
2. **Pullback:** có **≥ 2 nến đỏ** (`close < open`) trong **cửa sổ 5 phiên gần nhất**,
   tính TRƯỚC bar hiện tại.
3. **Đảo chiều xác nhận:** bar hiện tại `EMA(9)` cắt LÊN `EMA(21)` (phiên trước
   `EMA9 <= EMA21`, phiên này `EMA9 > EMA21`) **VÀ** MACD histogram > 0.

Tham số chốt TRƯỚC khi đo, **KHÔNG được tinh chỉnh trong lần đo đầu**:
- EMA nhanh/chậm/xu hướng = **9 / 21 / 200**
- MACD = **12 / 26 / 9** (histogram = MACD − signal)
- Pullback: **tối thiểu 2 nến đỏ / cửa sổ 5 phiên**
- `warmup_bars` = `max(200, 26+9) + 1`

Lọc VWAP trong mô tả gốc **không áp dụng** cho bar ngày (VWAP là khái niệm trong phiên) —
bỏ, và ghi rõ trong docstring là đã bỏ vì lý do gì.

## Luật ra lệnh

Bản gốc chỉ có TP, không có stop. Thay bằng:
- **Chốt lời:** `TP = giá vào + 2,0 × ATR(14)` tại thời điểm vào lệnh.
- **Cắt lỗ:** dùng `TrailingStopManager` **đã có sẵn** (`sl_multiplier=2.0`), không viết lại.
- Cả hai **phải tôn trọng T+2,5** — `PaperBroker` đã cưỡng chế sẵn từ `4a61186`, đừng đụng vào.

## Bộ lọc thanh khoản — ĐỌC KỸ, đây là chỗ dễ tự lừa mình nhất

Yêu cầu: chỉ giao dịch mã có **giá trị giao dịch bình quân 20 phiên ≥ 2 tỷ đồng**.

**TUYỆT ĐỐI KHÔNG dùng `symbol_universe.avg_value_20d`.** Bảng đó là ảnh chụp ngày
2026-08-13 (250/1.595 mã đạt ngưỡng). Lấy danh sách mã thanh khoản HÔM NAY rồi backtest
ngược về 2016 là **look-ahead bias**: bạn đang chọn sẵn những mã sau này trở nên lớn, và
kết quả sẽ đẹp một cách giả tạo.

Phải tính **tại từng thời điểm** (point-in-time), từ chính `bars_daily`:

```
gia_tri_gd(t)      = close(t) × volume(t)
binh_quan_20(t)    = trung bình gia_tri_gd của 20 phiên gần nhất, KHÔNG tính bar t
đủ điều kiện tại t <=> binh_quan_20(t) >= 2_000_000_000
```

Điều kiện này kiểm **tại bar sinh tín hiệu**: không đủ thanh khoản tại thời điểm đó thì
**bỏ qua tín hiệu**, không mua. Mã có thể đạt/không đạt ở các giai đoạn khác nhau — đó là
đúng ý.

**Cảnh báo đơn vị (đã trả giá 2 lần trong repo này):** `bars_daily` chứa giá **đã
back-adjust** (69% bar giá phân số), nên `close × volume` **không phải** giá trị giao dịch
danh nghĩa thật. Nêu rõ hạn chế này trong báo cáo, và nếu tìm được cách tốt hơn thì
**báo cáo chứ đừng tự đổi** — đổi định nghĩa bộ lọc giữa chừng là đổi luôn phép đo.

## Phạm vi đo

- Toàn bộ `bars_daily`, 2016-01-04 → 2026-08-13, khung `1d`.
- **Chạy độc lập từng mã**, cùng vốn mỗi mã (mặc định 1e9), rồi cộng dồn — KHÔNG chạy một
  danh mục chung (vốn chung sẽ cạn và lặng lẽ chặn tín hiệu các mã sau).
- So với **mua-và-giữ** cùng mã, cùng kỳ, cùng vốn, cùng phí. Thua mua-và-giữ = thất bại,
  in thẳng ra.

## Phạm vi phẫu thuật

ĐƯỢC tạo mới: `trading/strategies/octopus_pullback.py`, `tests/test_octopus_pullback.py`,
`scripts/measure_octopus.py`. Nếu cần EMA/MACD thì thêm vào `trading/indicators.py` (đã có
`AtrCalculator` ở đó — theo đúng style file này).

ĐƯỢC sửa tối thiểu: `trading/backtest.py` (chỉ đăng ký vào `STRATEGIES`),
`tests/test_backtest_cli.py` (chỉ thêm assert).

KHÔNG đụng: `trading/engine/`, `trading/real_orders.py`, `scripts/confirm_real_order.py`,
`config/config.yaml`, `trading/collector/`, `trading/paper_broker.py`. Không bật
`real_trading_enabled`. KHÔNG commit, KHÔNG push.

## Các bước và cách kiểm chứng

1. **EMA + MACD trong `trading/indicators.py`** (TDD, test đỏ trước).
   → Kiểm chứng: test với chuỗi giá đã biết đáp án; EMA seed bằng SMA của N giá trị đầu;
   MACD histogram đổi dấu đúng chỗ. Nêu rõ cách seed EMA trong docstring.
2. **`OctopusPullbackStrategy`** — interface duck-typed giống `DailyBreakoutStrategy`
   (`compute_crossover(bar) -> "bull"|"bear"|None`, `.qty`, `.warmup_bars`, `.last_atr()`).
   → Kiểm chứng: test từng điều kiện một — thiếu warmup → None; đủ 3 điều kiện → "bull";
   thiếu ĐÚNG MỘT điều kiện (dưới EMA200 / không đủ nến đỏ / EMA không cắt / histogram ≤ 0)
   → None. State không rò giữa hai symbol.
3. **Bộ lọc thanh khoản point-in-time.**
   → Kiểm chứng: test một chuỗi trong đó mã đạt ngưỡng ở giai đoạn giữa rồi tụt xuống —
   tín hiệu ở giai đoạn đủ thanh khoản được nhận, tín hiệu ngoài giai đoạn đó bị bỏ.
   Test riêng: cửa sổ 20 phiên KHÔNG tính bar hiện tại.
4. **Đăng ký `octopus_pullback` vào `STRATEGIES`.**
   → Kiểm chứng: `uv run pytest tests/test_backtest_cli.py -v` xanh + chạy CLI thật.
5. **Đo diện rộng** (`scripts/measure_octopus.py`).
   → Kiểm chứng: dán output THẬT, trả lời bằng số: (a) tổng PnL so mua-và-giữ và chênh
   lệch; (b) tổng số lệnh + số mã sinh lệnh + số mã từng đủ thanh khoản; (c) số dòng bị
   loại vì bẩn. Kèm phân phối theo mã (bao nhiêu mã thắng/thua BH, trung vị chênh lệch).
6. **Không làm hỏng thứ đang chạy.**
   → Kiểm chứng: `uv run pytest -m "not integration"` xanh toàn bộ; ruff không thêm lỗi mới
   (8 lỗi pre-existing ở scripts ngoài phạm vi — để nguyên).

## Ngoài phạm vi — cố ý không làm

- Không quét/tinh chỉnh tham số trong lần đo đầu. Muốn quét thì phải BIẾT có biên lợi thế
  trước đã, và khi quét phải báo cáo TOÀN BỘ lưới chứ không chỉ ô đẹp nhất.
- Không triển khai "Medium Long" / "Early Alert".
- Không chọn rổ mã theo kết quả.

## Môi trường

- Postgres đang chạy, `bars_daily` 2.969.328 dòng. DSN `127.0.0.1`, KHÔNG `localhost`.
- `ts` lưu UTC — đổi sang giờ HCM khi cần ngày giao dịch (đã có người lệch một ngày vì quên).
- Script mới: `sys.stdout.reconfigure(encoding="utf-8")`, nếu không sẽ chạy xong rồi mất
  sạch kết quả ở dòng print đầu tiên (console cp1252).
- Hook formatter reformat CẢ FILE sau mỗi Edit → `git diff --stat` sau khi sửa, revert phần
  phình ra ngoài phạm vi.
- `gitnexus_impact` trước khi sửa symbol có sẵn, `gitnexus_detect_changes` sau khi xong.

Nếu kết quả là "thua mua-và-giữ, không có biên lợi thế" thì đó là kết quả **hợp lệ và có
giá trị** — nó đóng một hướng bằng số liệu. Đừng chỉnh tham số cho đẹp số.
