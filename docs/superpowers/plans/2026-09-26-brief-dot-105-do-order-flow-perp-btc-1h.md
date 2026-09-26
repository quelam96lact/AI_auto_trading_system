# Brief đợt 105 — Order Flow có cứu được Donchian / Bollinger trên BTCUSDT perp 1H không?

Ngày giao: 26/09/2026. Base: main `6dc5c4e`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push**.

Nguồn chiến lược: file của chủ dự án `Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md` (gốc repo, chưa commit, **chỉ đọc, không sửa, không commit**).

## 0. Vì sao đợt này, và phạm vi

Chủ dự án muốn chuẩn bị giao dịch trên BingX. Hiện **chưa có chiến lược crypto nào có lợi thế đã đo**, nên chưa xây đường lệnh BingX. Đợt này trả lời đúng một câu hỏi:

> Thêm điều kiện **Order Flow** (taker-buy / delta) mà tài liệu yêu cầu thì module A (Donchian) và B (Bollinger) có lợi thế sau chi phí không?

Bối cảnh đã đo, **không đo lại**:
- **Đợt 37–38:** A và B **bản chỉ-giá** trên 2024-04 → 2026-09 cho kết quả "không có bằng chứng lợi thế" (phân vị 18–69%). Lúc đó bỏ Order Flow vì chưa có dữ liệu.
- **Đợt 40:** đã nạp dữ liệu Binance: nến 1H có `taker_buy_volume`, funding và OI.
- **Đợt 44:** module C (Funding–OI, thiếu vế liquidation) cho kết quả **ÂM**.

Những gì **loại khỏi đợt này**:
- **Module C:** không có dữ liệu liquidation lịch sử đầy đủ. Chính tài liệu ghi "thiếu dữ liệu → no-trade", và đợt 44 đã âm.
- **Module D (VWAP + Volume Profile):** cần viết module engine mới và nạp dữ liệu 5m. **Hoãn.** Chỉ làm nếu đợt này cho thấy Order Flow có giá trị.
- **Không** xây bộ chọn regime, **không** gộp module, **không** đụng gì tới BingX API hay API key.

## 1. Giả định (Claude đã kiểm 26/09)

- **Dữ liệu:** DB đang có `binance_klines` BTCUSDT 1h 2024-01-01 → 2026-08-31 (23.376 nến) và `binance_funding` 8h (2.922 dòng). **Chưa có 2020–2023.**
- **Loader:** `scripts/binance_vision.py` hỗ trợ `--mode klines|funding --symbol --interval --from --to`.
- **Engine:** `trading/perp_backtest.py::run_perp_backtest`. Module A ở đây dùng **mục tiêu cố định + dừng theo thời gian 24 nến**, không phải chốt 50% + chandelier. Tài liệu cho phép "target cố định" làm biến thể so sánh. **Giữ nguyên, không sửa logic thoát.**
- **Công cụ đối chứng:** `scripts/significance_test.py::run_null_simulation`. Nó bốc thăm điểm vào ngẫu nhiên, còn luật thoát giữ như thật; null A là 50/50, null B khớp tỷ lệ long thật.
- **Nguồn giá và flow:** Binance BTCUSDT USDⓈ-M. **Phí:** BingX taker `BINGX_PERP_TAKER` (0,05%) cho cả hai chiều. **Funding:** dùng funding của Binance làm đại diện cho BingX; báo cáo phải ghi rõ đây là giả định.
- **Flow lấy từ nến 1H** (cùng một nguồn cho cả hai cửa sổ), **không** lấy từ `binance_orderflow_1h`. Bảng đó dựng từ aggTrades và chỉ có từ 2024. Công thức:
  ```
  delta     = 2 * taker_buy_volume - volume
  buy_ratio = taker_buy_quote_volume / quote_volume
  delta_z_t = (delta_t - mean(delta_{t-240..t-1})) / std(delta_{t-240..t-1})   # chỉ quá khứ, không gồm t
  ```
  Nến có `volume <= 0`, `quote_volume <= 0`, thiếu trường taker, hoặc cửa sổ z chưa đủ 240 nến → flow **không hợp lệ** → **không vào lệnh**, và phải đếm số lần.
- **Niêm phong:** mọi dữ liệu **từ 2026-09-01** trở đi. Không nạp, không đọc.

## 2. Thiết kế đo chốt trước (không được đổi sau khi thấy kết quả)

**Tham số:** lấy nguyên từ tài liệu. **Không tối ưu, không quét lưới.** Vốn 500, `risk_fraction=0.005`, `max_leverage=10`, `slippage_bps=2.0` mỗi chiều. Module A **bật** lọc EMA50/EMA200, vì đó là "bản kết hợp khuyến nghị" §4.2.

**Điều kiện Order Flow**, xét tại lúc đóng nến tín hiệu `t`; lệnh vẫn đặt từ `t+1` như engine hiện có:

| Module | LONG | SHORT |
|---|---|---|
| A (§4.2) | `delta_t > 0` **và** `buy_ratio_t >= 0.55` | `delta_t < 0` **và** `buy_ratio_t <= 0.45` |
| B (§5.3, biến thể trade-delta) | `delta_z_t >= +0.5` | `delta_z_t <= -0.5` |

**Hai cửa sổ:**

| Cửa sổ | Khoảng (UTC) | Vai trò |
|---|---|---|
| **CHÍNH** | 2020-01-01 → 2023-12-31 | Chưa đợt nào chạy A/B 1H trên đây. **Phép thử quyết định.** |
| **LẶP LẠI** | 2024-01-01 → 2026-08-31 | Đã thấy bản chỉ-giá (đợt 37). Chỉ để xem kết quả có lặp lại không. |

Mỗi cửa sổ chạy engine độc lập; engine tự khởi động. Riêng `delta_z` tính trên chuỗi liên tục rồi tra theo `ts`, và chỉ dùng quá khứ.

**Chi phí:** phí và trượt giá đã nằm trong engine. Funding tính **sau** trên từng lệnh:
```
funding_cost = Σ rate(ft) * notional * (+1 nếu LONG, -1 nếu SHORT)
               với mọi ft trong (entry_ts, exit_ts];  notional = entry_price * qty
net_after_funding = net_pnl - Σ funding_cost
```
`funding_time` trong DB có lệch mili-giây (Claude thấy `16:00:00.001`). Trước khi so sánh, **cắt `ft` về giây**.

**Tiêu chí.** Một module **CÓ LỢI THẾ** chỉ khi đạt **cả bốn**:
1. Cửa sổ CHÍNH: số lệnh ≥ 30.
2. Cửa sổ CHÍNH: `net_after_funding > 0`.
3. Cửa sổ CHÍNH: vượt đối chứng ngẫu nhiên sau hiệu chỉnh Holm cho **2 giả thuyết** (A-flow, B-flow).
   - Với mỗi module, `p = (1 + #{null >= thật}) / (1 + N)` trên `net_pnl` **trước funding**. Cả thật lẫn null đều chưa trừ funding, nên so công bằng.
   - N = 1000. Lấy **p lớn hơn** trong hai null A/B, tức bảo thủ.
   - Holm: p nhỏ nhất phải ≤ 0,025, p còn lại ≤ 0,05.
4. Cửa sổ LẶP LẠI: `net_after_funding > 0`.

Thiếu bất kỳ điều nào → **KHÔNG CÓ BẰNG CHỨNG LỢI THẾ**.

**Chỉ báo cáo, không dùng để quyết định:**
- ablation flow **tắt** (tức bản đợt 37) trên cả hai cửa sổ;
- A với lọc EMA **tắt**;
- mua-giữ BTC từng cửa sổ;
- phân rã Long/Short và theo từng năm.

## 3. Phạm vi file

| File | Được làm gì |
|---|---|
| `trading/perp_backtest.py` | **Chỉ** thêm tham số `entry_filter: Callable[[Bar, Literal["LONG", "SHORT"]], bool] \| None = None` vào `run_perp_backtest`. Gọi nó đúng lúc tín hiệu thật đã đủ điều kiện ở nến `t`, **trước** khi tạo lệnh chờ; `False` thì bỏ tín hiệu. **Không** gọi trên nhánh `random_entry`. Không đổi gì khác. |
| `scripts/measure_perp_orderflow.py` | **Mới.** Chứa ba hàm thuần: loader từ `binance_klines`, hàm flow (`delta`, `buy_ratio`, `delta_z`) và hàm `funding_cost`. Chạy hai cửa sổ × hai module × (flow bật/tắt), gọi `run_null_simulation`, in bảng và kết luận theo §2. |
| `tests/test_measure_perp_orderflow.py` | **Mới.** |
| `tests/test_perp_backtest.py` | Chỉ **thêm** test cho `entry_filter`. |
| `docs/superpowers/research/2026-09-2x-dot-105-do-order-flow-perp-btc-1h.md` | **Mới.** Báo cáo. |

**Không được đụng:**
- `significance_test.py` (chỉ import), `measure_perp_modules.py`, `binance_vision.py` (chỉ chạy);
- mọi thứ trong `trading/engine`, `trading/collector`, `trading/storage`;
- `docker-compose.yml`, `config/`, file chiến lược của chủ dự án;
- container, Task Scheduler.

Không "tiện thể" refactor. Thấy lỗi ngoài phạm vi thì **báo lại**, không sửa.

**Loader:** trước khi viết loader mới, `grep` xem `scripts/leakage_audit.py`, `scripts/audit_information.py` và `scripts/event_study_module_c.py` đã có hàm đọc `binance_klines` trả về `Bar` hay chưa. Có thì import, rồi báo đã dùng hàm nào. **Không** chép công thức lần hai.

## 4. Các bước

**GitNexus trước khi sửa:** chạy `gitnexus_impact({target: "run_perp_backtest", direction: "upstream"})` và dán kết quả (người gọi, mức rủi ro). Nếu HIGH/CRITICAL thì **dừng lại và báo**. Sau khi sửa, chạy `gitnexus_detect_changes()` và dán kết quả.

1. **Đối chiếu engine với tài liệu, chỉ đọc.** Lập bảng `Điều kiện tài liệu (§) | Dòng code perp_backtest.py | Khớp?` cho A (§4.2–4.4) và B (§5.1–5.3), phần **giá**.
   → **Kiểm chứng bằng:** bảng đầy đủ. Chỗ nào lệch thì **ghi, không sửa**; Claude quyết.

2. **Nạp dữ liệu 2020–2023:**
   ```
   uv run python scripts/binance_vision.py --mode klines  --symbol BTCUSDT --interval 1h --from 2020-01-01 --to 2023-12-31
   uv run python scripts/binance_vision.py --mode funding --symbol BTCUSDT --from 2020-01-01 --to 2023-12-31
   ```
   → **Kiểm chứng bằng:** SQL đếm theo năm, dán output.
   - Kỳ vọng nến: 2020 = 8.784 (năm nhuận), 2021–2023 = 8.760 mỗi năm, tổng **35.064**.
   - Kỳ vọng funding khoảng **4.383** (3 lần/ngày).
   - Đếm số nến có `taker_buy_volume <= 0` hoặc `quote_volume <= 0`.
   - Lệch kỳ vọng thì **ghi nguyên văn** (Binance có thể thiếu giờ bảo trì). **Không** tự lấp.
   - Không đụng các dòng ≥ 2024: không `--force`.

3. **`entry_filter` trong engine (TDD).** Viết test trước, cho đỏ, rồi mới sửa:
   - `entry_filter=None` và `entry_filter=lambda b, d: True` cho **danh sách lệnh giống hệt** bản cũ trên cùng fixture.
   - `lambda b, d: False` → 0 lệnh, với cả hai module.
   - Filter được gọi với đúng `Bar` của nến tín hiệu `t` và đúng chiều. Dùng spy để ghi `ts` và chiều, rồi đối chiếu: lệnh khớp sớm nhất ở nến `t+1`.
   - Khi `random_entry` được đặt, filter **không** được gọi.

   → **Kiểm chứng bằng:** `uv run pytest tests/test_perp_backtest.py -v`, toàn bộ xanh, gồm cả các test cũ của đợt 37–38.

4. **Hàm thuần trong script (TDD):**
   - `delta` và `buy_ratio` khớp số tính tay trên 2 nến.
   - `delta_z` tại `t` **không đổi** khi sửa nến `t` hoặc `t+1`; test này chống nhìn trộm tương lai. Nó ra "không hợp lệ" khi chưa đủ 240 nến và khi std = 0.
   - Nến không hợp lệ (volume 0) cho flow "không hợp lệ", tức filter trả `False`.
   - `funding_cost`: một ví dụ tính tay cho LONG trả tiền khi rate dương, và SHORT nhận tiền. Funding đúng bằng `entry_ts` **không** tính; đúng bằng `exit_ts` **có** tính.
   - Ngưỡng A: `buy_ratio = 0.55` → LONG hợp lệ; `0.5499` → không.

   → **Kiểm chứng bằng:** `uv run pytest tests/test_measure_perp_orderflow.py -v`, toàn bộ xanh.

5. **Phá thử.**
   - Đổi dấu điều kiện LONG/SHORT của A trong hàm flow → phải có test đỏ.
   - Cho `delta_z` gồm cả nến `t` trong cửa sổ → phải có test đỏ.

   Sao lưu **ra ngoài repo** trước khi phá, rồi khôi phục bằng bản sao lưu đó. **Cấm `git checkout`, `git restore`, `git stash`.**
   → **Kiểm chứng bằng:** dán tên test đỏ cho mỗi lần phá, rồi dán lần chạy xanh sau khi khôi phục.

6. **Chạy đo:** `uv run python scripts/measure_perp_orderflow.py`. Script in các bảng sau cho mỗi cửa sổ × module × (flow bật/tắt):
   - số lệnh; số tín hiệu bị flow chặn; số tín hiệu bị bỏ vì flow không hợp lệ;
   - `net_pnl`; tổng funding; `net_after_funding`; win rate; profit factor; max drawdown;
   - Long/Short riêng; theo từng năm;
   - mua-giữ BTC.

   Cửa sổ CHÍNH có thêm p của null A và null B (N=1000), p đã chọn, và Holm. Cuối cùng là **một dòng kết luận mỗi module** theo đúng §2.
   → **Kiểm chứng bằng:** dán **nguyên văn** toàn bộ output vào báo cáo.

7. **Kiểm tra toàn cục:**
   - `uv run pytest -m "not integration" -q`: không có test đỏ mới so với base (1053 passed).
   - `uv run ruff check trading tests scripts/measure_perp_orderflow.py`: sạch.

## 5. Báo cáo cho Claude

File `docs/superpowers/research/2026-09-2x-dot-105-do-order-flow-perp-btc-1h.md`, theo thứ tự:
1. Kết luận hai dòng.
2. Bảng §4.1.
3. Số liệu nạp §4.2.
4. Output test.
5. Kết quả phá thử.
6. Output đo nguyên văn.
7. `gitnexus_impact` và `detect_changes`.
8. Những điều thấy ngoài phạm vi.

**Không** viết "có tiềm năng", "đáng chú ý" hay "gần đạt". Chỉ viết kết luận theo tiêu chí §2.

Kết thúc bằng câu: "Tôi không commit, không push, không đụng BingX API, không đọc dữ liệu từ 2026-09-01."
