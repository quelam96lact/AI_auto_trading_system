# Brief đợt 107 — Tái dựng take-profit của octopus sau khi engine khởi động lại

Ngày giao: 26/09/2026. Base: main `1701aa8`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push, không build/restart container**.

## 0. Lỗi

`OctopusPullbackStrategy` giữ mức chốt lời trong dict in-memory `self._tp` (`trading/strategies/octopus_pullback.py:128`). Mức này được đặt ở bar **đầu tiên** mà `on_bar` thấy đang giữ vị thế (dòng 217–223):

```python
tp = bar.open + self.tp_atr_mult * atr
```

Engine khởi động lại thường xuyên: đợt 96 đếm được 11 lần trong 7 ngày. Sau mỗi lần khởi động lại, `_tp` rỗng, nên bar đầu tiên của phiên mới **neo lại** TP theo giá mở cửa **hôm đó**. Hệ quả:
- **Giá đã tăng từ lúc mua:** TP bị đẩy lên theo, có thể không bao giờ chạm tới.
- **Giá đã giảm:** TP bị kéo xuống. Lệnh "chốt lời" khi đó thực chất là **bán lỗ**, dưới giá vốn.

Ví dụ IJC (bảng `orders`, Claude kiểm 26/09): BUY ngày 03/09 giá 7.353,675, hiện giá khoảng 6.720. Mỗi lần khởi động lại, TP của IJC bị neo về khoảng 6.720 + 2·ATR, thay cho 7.353 + 2·ATR.

Luật chốt lời vì thế **chạy khác hẳn** luật đã backtest, và **không có cảnh báo nào**. Đây là cùng một lớp lỗi với RESTORE-1 (trailing stop mất `_highest`) và đợt 96 (lô khôi phục bị đông cứng). Hai lỗi đó đã được sửa bằng cách **dựng lại trạng thái từ dữ liệu trong DB lúc khởi động**; đợt này làm đúng như vậy cho TP.

## 1. Định nghĩa chốt trước — TP khôi phục phải **bằng đúng** TP mà luồng sống đã tính

TP sống được tính tại **bar neo `A`**, tức bar đầu tiên `on_bar` thấy `held > 0` sau lệnh BUY:

```
TP = open_A + tp_atr_mult · ATR_A
```

`ATR_A` là ATR của chiến lược sau khi đã cập nhật bar `A`.

Khi khôi phục, dựng lại đúng công thức đó từ DB:
1. Lấy lệnh BUY gần nhất của mã trong bảng `orders`: `ts` và `price`.
2. **Tìm bar neo `A`** trong bảng `bars` theo đúng quan hệ giữa `Fill.ts` và bar mà luồng sống dùng. Luật này có thể là "bar đầu tiên có `ts > fill.ts`" hoặc "`ts >= fill.ts`". **Agent phải đọc code để xác định** (bước 1), trích dẫn số dòng, và ghim bằng test. Không đoán.
3. `ATR_A`: cho một `AtrCalculator` **mới**, cùng `atr_period` của chiến lược, chạy qua `strategy.warmup_bars` bar kết thúc tại `A` (gồm cả `A`). Làm vậy tức là coi như engine vừa khởi động và warm-up ngay tại `A`. Đó cũng là quy ước warm-up hiện có ở `main.py:255–268`.
4. `TP = open_A + tp_atr_mult · ATR_A`. Dùng **chung một hàm** với luồng sống; công thức chỉ được tồn tại ở một chỗ.

**Không khôi phục được** thì phát **WARN** nêu tên mã và lý do, rồi để luồng sống neo lại như hiện nay. Ba lý do có thể:
- không có BUY;
- không có bar nào sau lệnh BUY;
- có ít hơn `atr_period + 1` bar trước `A`.

Tuyệt đối không im lặng. Làm đúng khuôn trailing stop ở `main.py:277–291`.

## 2. Phạm vi file

| File | Được làm gì |
|---|---|
| `trading/strategies/octopus_pullback.py` | Tách `_tp_level(anchor_open, atr) -> float`, dùng cho **cả** `on_bar` lẫn khôi phục. Thêm `restore_take_profit(symbol, bars_until_anchor: list[Bar]) -> float \| None`: chiến lược tự chạy ATR mới trên các bar truyền vào, lấy `open` của bar cuối làm neo, rồi ghi vào `_tp`. Trả `None` nếu không đủ bar. Lưu `atr_period` thành thuộc tính nếu cần. **Không** đổi logic tín hiệu. |
| `trading/strategy.py` | Thêm `@runtime_checkable class RestoresTakeProfit(Protocol)` với đúng một phương thức `restore_take_profit`. `main.py` kiểm bằng `isinstance`. **Không** dùng `hasattr`. |
| `trading/storage/db.py` | Thêm `read_last_buy_fill(symbol) -> tuple[datetime, float] \| None` và `read_bars_until(symbol, until_ts, n) -> list[Bar]` (n bar cuối có `ts <= until_ts`, sắp tăng dần), cùng phương thức tìm bar neo cần cho §1 bước 2. Viết SQL theo khuôn `read_highest_since_buy`. |
| `trading/engine/main.py` | Sau khối khôi phục trailing stop: với mỗi vị thế `qty > 0`, nếu chiến lược thoả `RestoresTakeProfit` thì khôi phục TP. Thành công → alert INFO (mã, neo, ATR, TP). Thất bại → WARN theo §1. |
| Fake storage trong test | Thêm đúng các phương thức mới. |
| `tests/test_octopus_pullback.py`, `tests/test_engine_main*.py` (tên thật agent tự tìm) | Chỉ **thêm** test. |

**Không được đụng:**
- `trading/strategies/octopus_combo.py`: cùng lỗi, nhưng không chạy thật. **Chỉ báo lại.**
- `trailing_stop.py`, `paper_broker.py`, `logic.py`, `real_orders.py`, collector, config, `docker-compose.yml`, Task Scheduler.

Không "tiện thể" refactor. Thấy lỗi ngoài phạm vi thì báo, không sửa.

## 3. Các bước

**GitNexus TRƯỚC khi sửa.** Chạy `gitnexus_impact` (upstream) cho `OctopusPullbackStrategy`, `on_bar` của nó và hàm chạy engine trong `main.py`, rồi dán kết quả. Nếu HIGH hoặc CRITICAL thì **dừng lại và báo**. Cuối đợt chạy `gitnexus_detect_changes()` và dán kết quả.

1. **Chỉ đọc: xác định bar neo.** Truy từ `on_bar` trả về BUY, qua `logic.py` và `paper_broker`, tới `storage.write_order(fill)`:
   - `Fill.ts` được gán bằng gì?
   - Bar nào là bar đầu tiên `on_bar` thấy `held > 0`?

   → **Kiểm chứng bằng:** trích dẫn các dòng code và một câu kết luận dạng `A = bar đầu tiên có ts > fill.ts` hoặc `ts >= fill.ts`.

2. **Test tương đương (TDD, viết test đỏ trước).** Đây là test quan trọng nhất của đợt.
   - Cho một chiến lược "sống" đi qua một chuỗi bar giả dài `warmup_bars + vài bar`.
   - Giả lập vị thế xuất hiện theo đúng luật ở bước 1, rồi ghi lại `_tp` sống.
   - Cho một chiến lược **mới** gọi `restore_take_profit` với **đúng** `warmup_bars` bar kết thúc tại `A`. Chuỗi bar sống cũng phải dài đúng từng đó bar, tính đến `A`.
   - Hai giá trị TP phải **bằng nhau tuyệt đối** (`==`, không dùng `approx`).

   Thêm hai test:
   - không đủ bar → trả `None`, không ghi `_tp`;
   - sau khi khôi phục, `on_bar` ở bar sau **không** neo lại TP. Nó dùng TP đã khôi phục: bar có `close >= TP_khôi_phục` thì ra SELL, bar có `close` thấp hơn thì không.

   → **Kiểm chứng bằng:** `uv run pytest tests/test_octopus_pullback.py -v`, toàn bộ xanh.

3. **Storage.** Test SQL bằng integration test (DB `trading_test`) nếu repo đã có khuôn đó. Không có khuôn thì dùng fake và giải thích lý do.
   - `read_last_buy_fill` lấy BUY **muộn nhất** và bỏ qua SELL.
   - `read_bars_until` trả đúng n bar, sắp tăng dần, gồm cả bar tại `until_ts`.

   → **Kiểm chứng bằng:** pytest.

4. **main.py (TDD với fake storage, theo khuôn test RESTORE-1 hiện có).**
   - Có vị thế và có BUY cùng bar → INFO kèm TP đúng, và `strategy._tp[sym]` đã được đặt.
   - Không có BUY → WARN chứa tên mã.
   - Chiến lược không thoả `RestoresTakeProfit`, ví dụ SMA cross → không gọi, không WARN.

   → **Kiểm chứng bằng:** pytest.

5. **Phá thử.** Sao lưu **ra ngoài repo** rồi khôi phục từ bản sao lưu đó. **Cấm `git checkout`, `git restore`, `git stash`.** Mỗi phép phá phải làm ít nhất một test đỏ:
   - (i) neo `A` lệch một bar so với luật ở bước 1;
   - (ii) `restore_take_profit` dùng `close` thay cho `open` làm neo;
   - (iii) nhánh WARN bị xoá, tức thất bại mà im lặng.

   Phép phá phải thật sự vi phạm luật. Đợt 105 và 106 đều có phép phá "vô hiệu"; kiểm lại trước khi kết luận là test không bắt được.
   → **Kiểm chứng bằng:** dán tên test đỏ cho từng phép phá, rồi dán lần chạy xanh sau khi khôi phục.

6. **Chạy khô trên DB thật, chỉ đọc.** Viết script tạm **ngoài repo**, gọi các hàm storage mới cùng `restore_take_profit` cho IJC và AAA. In ra: BUY (ts, giá), bar neo `A` (ts, open), `ATR_A`, TP khôi phục; và để so sánh, TP mà code hiện tại sẽ neo (open của bar mới nhất + 2·ATR).
   - **Không** ghi DB, **không** restart engine.

   → **Kiểm chứng bằng:** dán output nguyên văn.

7. **Kiểm tra toàn cục:**
   - `uv run pytest -m "not integration" -q`: không test cũ nào đỏ (mốc 1120 passed).
   - Suite integration, nếu có đụng storage: `docker compose --profile test up -d nats-test`, rồi `uv run pytest -m integration -q`.
   - `uv run ruff check trading tests`: sạch.

## 4. Triển khai

**Agent không build và không restart.** Claude audit, commit, rồi tự rebuild engine **sau khi Lượt A của brief 104 xong**, tức sau 15:40 thứ Hai 28/09. **Không** triển khai trước phiên thứ Hai.

Lý do: sửa lỗi này **làm đổi hành vi của IJC/AAA ngay phiên đầu tiên**. Claude kiểm bảng `orders` ngày 26/09:

| Mã | BUY | Giá mua | Giá gần đây |
|---|---|---:|---:|
| IJC | 03/09 09:15 | 7.353,675 | ~6.720 |
| AAA | 03/09 09:20 | 7.053,525 | ~7.470 |

- Với AAA, TP khôi phục bằng 7.05x + 2·ATR **có thể nằm dưới giá hiện tại**, nên có thể ra SELL "chốt lời" ngay bar đầu.
- Với IJC, TP khôi phục cao hơn giá hiện tại, nên không kích hoạt.

Brief 104 đang đo engine **hiện tại** (bán bằng stop). Triển khai trước thứ Hai sẽ trộn hai thay đổi vào một phép nghiệm thu. Bước 6 phải in rõ, với từng mã, TP khôi phục so với giá đóng cửa gần nhất: **TP ≤ giá hiện tại → cờ "SẼ BÁN NGAY KHI TRIỂN KHAI"**. Không diễn giải thêm.

## 5. Báo cáo cho Claude

Báo cáo gồm các phần sau, theo thứ tự:
1. Kết luận bước 1 kèm trích dẫn code.
2. Output các lượt test đỏ rồi xanh.
3. Kết quả phá thử.
4. Output chạy khô trên IJC và AAA.
5. `gitnexus_impact` (chạy **trước** khi sửa) và `detect_changes`.
6. Những điều thấy ngoài phạm vi, **bắt buộc** gồm `octopus_combo`.

Kết thúc bằng câu: "Tôi không commit, không push, không build hay restart container, không ghi DB thật."
