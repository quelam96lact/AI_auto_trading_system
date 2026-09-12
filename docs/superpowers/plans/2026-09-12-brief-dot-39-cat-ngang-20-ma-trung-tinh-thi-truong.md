# Brief đợt 39 — Động lượng cắt ngang 20 mã, trung tính thị trường

Ngày giao: 12/09/2026.
Base: `45dd07f` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

Hướng này do chủ dự án chốt sau khi đợt 38 kết luận cả hai module một-mã đều không có bằng
chứng lợi thế.

---

## 0. Vì sao trục này, và ba cái bẫy trong dữ liệu

### 0.1. Điều đợt 37 và 38 đã loại trừ

Sáu chiến lược đã đo, sáu lần âm. Đợt 38 chỉ ra vì sao: điểm vào lệnh của Donchian và
Bollinger nằm ở phân vị 19% và 39% của nhiễu ngẫu nhiên trên IS — **tệ hơn bốc thăm**.

Và đợt 37 phơi ra một giả tạo cụ thể: Donchian "lãi" ở OOS với **18 lệnh short trên 8 long**
trong năm BTC giảm 10%. Đó là cược hướng, không phải kỹ năng.

**Danh mục trung tính thị trường triệt tiêu tận gốc giả tạo đó.** Long một rổ, short một rổ,
giá trị bằng nhau — thị trường lên hay xuống đều không tự sinh lãi. Cái còn lại đúng là: *xếp
hạng theo động lượng có phân biệt được mã mạnh với mã yếu hay không.* Một câu hỏi khác hẳn
câu hỏi định thời điểm mà sáu lần trước đã hỏi và đã trả lời là không.

Và ta có phần dư để khai thác. Tôi đo tương quan lợi suất ngày với BTC:

```
ETH 0.825 | SOL 0.789 | DOGE 0.783 | ADA 0.698 | ... | XAUT 0.299 | TRX 0.185
```

Trung vị ~0,64. Không phải 20 mã nhảy như một.

### 0.2. Bẫy 1 — sáu ngày cuối chỉ có HAI mã

```
 2026-09-02 |    20
 2026-09-03 |     2      <-- chỉ còn BTC và ETH
 ...
 2026-09-08 |     2
```

Đợt 37 và 38 chạy trên BTC một mã nên không thấy gì. Một chiến lược cắt ngang chạy tới
`2026-09-08` sẽ xếp hạng **một rổ hai phần tử** trong sáu ngày cuối và cho ra rác — mà rác đó
trông vẫn như số liệu bình thường.

**Ngày cuối của mọi phép đo đợt này là `2026-09-02`, không phải `2026-09-08`.** Đây là khác
biệt có chủ ý so với đợt 37/38; đừng "sửa cho nhất quán".

### 0.3. Bẫy 2 — vũ trụ mã lớn dần theo thời gian

| Mốc | Số mã có dữ liệu |
|---|---|
| 2021-05-14 | 2 |
| 2022-02-15 | **10** |
| 2024-01-01 | 15 |
| 2025-06-01 | 19 |
| 2026-01-01 | 20 |

Không phải 20 mã tồn tại suốt. Xếp hạng "top 3 / bottom 3" trên một rổ 10 mã khác hẳn trên rổ
20 mã. Vũ trụ phải được tính **lại tại từng ngày tái cân bằng**, không bao giờ cố định.

`2022-02-15` là ngày đầu tiên đủ 10 mã — tôi đã đo.

### 0.4. Bẫy 3 — LDO có một lỗ hổng 310 ngày liền

```
 truoc_lo   |   sau_lo   | so_ngay_thieu
 2022-11-17 | 2023-09-24 |           310
```

Một lỗ liền mạch, không rải rác. ETH thiếu 3 ngày lẻ; 18 mã còn lại liền mạch.

Nếu tính lợi suất `close_t / close_{t-30}` mà không kiểm tra cửa sổ có đủ dữ liệu không, LDO
sẽ nhảy vào bảng xếp hạng với một "lợi suất 30 ngày" thực chất trải 340 ngày — và gần như
chắc chắn đứng đầu hoặc cuối bảng. Một mã hỏng dữ liệu chiếm chỗ trong rổ 3 mã là hỏng
1/3 danh mục.

### 0.5. Thiên lệch sống sót — phải nói ra, không sửa được

20 mã này được **chọn theo khối lượng năm 2026 rồi đo lùi về quá khứ** (ghi trong docstring
`scripts/measure_crypto_strategies.py`). Những đồng đã chết không có trong đó.

Với long-short động lượng, thiên lệch này **bơm phồng vế long**: mọi mã trong rổ đều là mã đã
sống sót tới 2026. Không có cách nào sửa bằng dữ liệu hiện có. **Phải in thành cảnh báo bắt
buộc trong mọi báo cáo**, cùng hạng với cảnh báo funding.

---

## 1. Phạm vi

### 1.1. File được sửa — chỉ bốn file, tất cả đều mới

| File | Việc |
|---|---|
| `trading/cross_sectional.py` | engine danh mục cắt ngang |
| `scripts/measure_cross_sectional.py` | CLI đo lường + phân phối null + báo cáo |
| `tests/test_cross_sectional.py` | test |
| `docs/superpowers/research/2026-09-12-dot-39-cat-ngang-20-ma.md` | kết quả |

**Không sửa file có sẵn nào.** Bao gồm `trading/perp_backtest.py`,
`scripts/significance_test.py`, `scripts/measure_perp_modules.py`, `trading/indicators.py`,
`trading/backtest.py`, `trading/crypto_fees.py`, và mọi thứ trong `trading/collector/`,
`trading/engine/`, `trading/strategies/`.

Được **import** thoải mái: `trading.crypto_fees.BINGX_PERP_TAKER`, `trading.metrics.*`,
`trading.models.Bar`, `trading.data_quality.is_dirty_bar`,
`scripts.measure_crypto_strategies.read_crypto_bars`.

### 1.2. Ràng buộc vận hành

Giữ nguyên toàn bộ ràng buộc đợt 37/38: không gọi mạng, chỉ đọc DB, không đụng NATS,
`real_trading_enabled` giữ `false`, không in secret, không xoá file, **không commit, không
push**. Mọi output dán vào báo cáo copy từ terminal. Thiếu thì ghi **"CHƯA LÀM"** kèm lý do,
**không bịa**.

**GitNexus:** `npx gitnexus analyze` trước và sau; `gitnexus_detect_changes()` khi xong. MCP
timeout thì ghi rõ.

---

## 2. Quy ước bắt buộc

### 2.1. Khung ngày, không phải khung giờ

Dùng `interval='1d'`. Lý do: động lượng cắt ngang là hiện tượng khung ngày/tuần; ở khung 1H
chi phí quay vòng sẽ nuốt hết trước khi tín hiệu kịp nói gì. Ta cũng có lịch sử dài hơn nhiều
ở khung ngày.

Toàn bộ mốc thời gian là **UTC**, in ra phải kèm hậu tố `UTC`.

### 2.2. Tách mẫu

| Tập | Khoảng | Vũ trụ |
|---|---|---|
| **IS** | `2022-02-15` → `2025-12-31` | 10 → 18 mã |
| **OOS** | `2026-01-01` → **`2026-09-02`** | 20 mã |

Mốc cố định trong code, không cho truyền qua CLI. **OOS chạy đúng một lần, cuối cùng.** Xem
OOS rồi chỉnh tham số thì kết quả không còn là OOS — nếu lỡ làm, ghi thẳng vào báo cáo.

### 2.3. Điều kiện đủ tư cách vào bảng xếp hạng

Tại mỗi ngày tái cân bằng `t`, một mã đủ tư cách khi **cả ba** đúng:

1. Có nến ngày tại đúng `t`.
2. Có nến ngày tại đúng `t - lookback`.
3. Số nến ngày trong khoảng `(t - lookback, t]` **≥ `0.9 * lookback`**.

Điều 3 là thứ chặn LDO trong 310 ngày lỗ hổng (§0.4), và cũng khoan dung với 3 ngày thiếu lẻ
của ETH. **Không nội suy, không điền giá, không dùng nến gần nhất thay thế.** Mã không đủ tư
cách thì đứng ngoài kỳ đó.

Bỏ nến rác bằng `is_dirty_bar` trước mọi tính toán.

### 2.4. Chống nhìn trước

- Xếp hạng tính bằng giá đóng cửa ngày `t`.
- **Giao dịch khớp tại giá mở cửa ngày `t+1`.** Không bao giờ khớp tại close của ngày ra tín hiệu.
- Nếu một mã không có nến `t+1` → không vào vị thế mã đó kỳ này; ghi vào `skipped_fills`.

### 2.5. Chi phí

- `fee_rate = BINGX_PERP_TAKER` (import, **không gõ lại số**), áp cho **mọi đơn vị được mua
  hoặc bán**, cả hai chiều.
- **Quay vòng có nhận biết:** khi tái cân bằng, chỉ giao dịch phần **chênh lệch** giữa danh
  mục cũ và mới. Một mã ở lại cùng vế với cùng tỷ trọng thì chỉ trả phí cho phần điều chỉnh
  khối lượng, không trả phí đóng-rồi-mở-lại. Tính sai chỗ này sẽ thổi phồng chi phí gấp nhiều
  lần và làm kết luận vô nghĩa.
- `slippage_bps` là tham số **bắt buộc khai báo tường minh**. Baseline `0.0`; §5 có một lượt `2.0`.
- **Funding không mô hình hoá** — hạn chế đã biết, in thành cảnh báo. Vế short *nhận* funding
  trong thị trường tăng và *trả* trong thị trường giảm; bỏ qua nó là bỏ qua một khoản có thể
  cùng bậc độ lớn với kết quả.

### 2.6. Danh mục

- Vốn `500 USDT`, không đòn bẩy: **tổng giá trị danh nghĩa hai vế = vốn**.
- Mỗi vế `capital / 2`. Trong vế, **chia đều** cho `k` mã.
- `k = 3` (long 3 mã đầu bảng, short 3 mã cuối bảng).
- Bỏ qua kỳ tái cân bằng nào có **dưới 10 mã đủ tư cách** — không hạ `k` để lấp chỗ.
- Tái cân bằng **mỗi 7 ngày lịch**.
- **Không thanh lý, không ký quỹ.** Gross 1×, net 0 nên rủi ro thanh lý coi như không có; ghi
  rõ giả định này thay vì mô phỏng.

---

## Task 1 — Engine `trading/cross_sectional.py`

### 1.1. Kiểu dữ liệu

```python
@dataclass
class Rebalance:
    ts: datetime                    # ngày ra tín hiệu (close), UTC
    fill_ts: datetime               # ngày khớp lệnh (open t+1), UTC
    universe_size: int
    longs: list[str]
    shorts: list[str]
    turnover_notional: float        # tổng giá trị danh nghĩa đã giao dịch kỳ này
    fees: float
    skipped_fills: int              # mã thiếu nến t+1

@dataclass
class CrossSectionalReport:
    starting_capital: float
    ending_capital: float
    equity_curve: list[tuple[datetime, float]]   # theo ngày
    rebalances: list[Rebalance]
    total_fees: float
    skipped_rebalances: int         # kỳ bỏ vì vũ trụ < 10
```

### 1.2. Hàm chính

```python
def run_cross_sectional(
    bars_by_symbol: dict[str, list[Bar]],
    *,
    start: datetime,
    end: datetime,
    lookback_days: int = 30,
    rebalance_days: int = 7,
    k: int = 3,
    min_universe: int = 10,
    capital: float = 500.0,
    fee_rate: float,            # BẮT BUỘC tường minh
    slippage_bps: float,        # BẮT BUỘC tường minh
    skip_recent_days: int = 0,  # biến thể: bỏ qua N ngày gần nhất khi tính động lượng
    selector: Callable | None = None,   # None = xếp hạng động lượng; dùng cho đối chứng
) -> CrossSectionalReport:
```

Tham số `selector` là **cả lý do đợt 38 tồn tại**: nó cho phép thay **đúng một thứ** — cách
chọn mã — mà giữ nguyên mọi thứ khác. Chữ ký:

```python
selector(eligible: list[str], returns: dict[str, float], k: int, rng) -> tuple[list[str], list[str]]
```

`None` → dùng xếp hạng động lượng thật. Đối chứng ngẫu nhiên truyền một selector bốc thăm.
**Không viết hai engine.**

### 1.3. Công thức động lượng

```
ret(sym) = close[t - skip_recent_days] / close[t - lookback_days] - 1
```

`skip_recent_days = 0` ở baseline. Xếp giảm dần: `k` mã đầu là **long**, `k` mã cuối là **short**.

### 1.4. Đường vốn

Ghi `equity` **mỗi ngày** (không chỉ mỗi kỳ tái cân bằng) — cần cho max drawdown và Sharpe
trung thực. Mỗi ngày, lãi/lỗ chưa thực hiện của từng vị thế tính theo close ngày đó.

`periods_per_year = 365.0` cho Sharpe (khung ngày).

### 1.5. Kiểm chứng Task 1 — `tests/test_cross_sectional.py`

Mỗi test dựng panel thủ công, không đọc DB, không gọi mạng.

**Nhóm đúng đắn cơ bản:**

1. Panel 10 mã, một mã tăng đều mạnh nhất và một mã giảm đều mạnh nhất → mã tăng nằm trong
   `longs`, mã giảm nằm trong `shorts`.
2. **Trung tính thị trường:** panel mà **mọi** mã tăng cùng một tỷ lệ phần trăm mỗi ngày →
   PnL trước phí **xấp xỉ 0** (dung sai nhỏ). Đây là bài test chứng minh thiết kế thật sự
   trung tính; nếu nó đỏ thì có lỗi trọng số giữa hai vế.
3. Tổng giá trị danh nghĩa vế long bằng vế short tại mọi kỳ tái cân bằng.

**Nhóm dữ liệu bẩn — chính là ba cái bẫy ở §0:**

4. **Mã có lỗ hổng bị loại:** panel trong đó một mã thiếu 50% số ngày trong cửa sổ lookback →
   mã đó **không** xuất hiện trong `longs` lẫn `shorts`, dù lợi suất hai đầu mút của nó là
   cực trị. Đây là bài test LDO.
5. **Vũ trụ co lại:** panel mà số mã đủ tư cách tụt xuống 9 trong một giai đoạn → các kỳ đó
   nằm trong `skipped_rebalances`, **không** có giao dịch nào.
6. Mã thiếu nến `t+1` → không vào vị thế mã đó, `skipped_fills` tăng.

**Nhóm chống nhìn trước và chi phí:**

7. **Mọi** `Rebalance` có `fill_ts > ts`. Viết thành một test quét toàn bộ.
8. **Quay vòng có nhận biết:** hai kỳ liên tiếp cho ra **cùng** danh sách long/short và giá
   không đổi → phí kỳ thứ hai **bằng 0** (hoặc chỉ là phần điều chỉnh khối lượng rất nhỏ, nêu
   rõ dung sai). Test này bắt đúng lỗi đóng-rồi-mở-lại ở §2.5.
9. Phí một kỳ bằng đúng `turnover_notional * fee_rate`, tính lại trong test.

**Nhóm selector:**

10. `selector` bốc thăm với cùng hạt giống → kết quả tất định, chạy hai lần giống hệt.
11. `selector` trả về đúng `k` mã mỗi vế, không trùng nhau giữa hai vế.

**Tiêu chí đạt Task 1:** 11 test pass, ruff sạch, suite đầy đủ pass (mốc hiện tại **697**),
**cổng cứng VN khớp từng chữ số**:

```
-1,615,319,902 | BH 1,897,587,481,903 | 1,514 lệnh | 439 mã
```

*(Đợt này không đụng file nào của đường VN, nên cổng cứng chỉ là lưới an toàn — nhưng vẫn chạy
và vẫn dán đủ bốn con số.)*

---

## Task 2 — `scripts/measure_cross_sectional.py`

**Chỉ bắt đầu sau khi Task 1 đạt toàn bộ.**

### 2.1. Ba thứ nó phải in

**(a) Kết quả thật** — các cột:

`rebalances` | `skipped_rebalances` | `skipped_fills` | `net_pnl` | `net_pnl_pct` |
`profit_factor` | `max_dd` | `sharpe` | `total_fees` | `turnover_tong` | `universe_tb`

`profit_factor` tính trên lãi/lỗ **từng kỳ tái cân bằng** (không phải từng mã).

**(b) Hai mốc đối chứng**, cùng kỳ, cùng vốn, cùng phí:

- Mua-và-giữ **BTC**.
- Mua-và-giữ **chia đều toàn vũ trụ** (tái cân bằng cùng nhịp 7 ngày, chỉ long, không short).
  Đây mới là mốc đúng cho một chiến lược đa mã.

**(c) Phân phối null từ đối chứng danh mục ngẫu nhiên** — cùng ngày tái cân bằng, cùng `k`,
cùng điều kiện đủ tư cách, cùng phí; **chỉ thay cách chọn mã bằng bốc thăm** từ đúng tập mã
đủ tư cách hôm đó. `1000` hạt giống, `random.Random(seed)` cô lập.

In: trung vị, p05, p25, p75, p95, p99, và **phân vị của kết quả thật**.

Theo đúng khuôn của `scripts/significance_test.py` (đợt 38) — đọc file đó trước, giữ cùng
cách trình bày. **Không sửa file đó**, không import cấu trúc nội bộ của nó; chép khuôn báo
cáo thì được, nhưng nói rõ trong báo cáo là đã chép.

Ở đây **không cần hiệu chỉnh xác suất** như đợt 38: số kỳ tái cân bằng và số vị thế giống hệt
nhau theo thiết kế. Nêu điều đó trong output, thay cho khối hiệu chỉnh.

### 2.2. Ba cảnh báo bắt buộc in mỗi lần chạy

1. `[THIÊN LỆCH SỐNG SÓT]` — 20 mã chọn theo khối lượng 2026 đo lùi về quá khứ; đồng đã chết
   không có trong rổ; thiên lệch này bơm phồng vế long. Không sửa được bằng dữ liệu hiện có.
2. `[CHƯA MÔ HÌNH HOÁ FUNDING]` — vế short nhận/trả funding tuỳ chế độ thị trường, khoản này
   có thể cùng bậc độ lớn với kết quả.
3. `[VŨ TRỤ THAY ĐỔI]` — kèm số mã đủ tư cách **nhỏ nhất, lớn nhất và trung bình** thật của
   lượt chạy đó.

### 2.3. Tham số

```
--split        is | oos            (mặc định is)
--lookback     mặc định 30
--rebalance    mặc định 7
--k            mặc định 3
--skip-recent  mặc định 0
--iterations   mặc định 1000
--capital / --slippage-bps / --dsn
```

`--split oos` in cảnh báo đỏ như đợt 38: *"OOS chỉ chạy MỘT LẦN sau khi tham số đã khoá."*

### 2.4. Kiểm chứng Task 2

1. Chạy hai lần cùng tham số → output giống hệt. Dán bằng chứng `diff`.
2. **Mốc mua-và-giữ BTC trên tập IS phải tái lập được.** Chạy một lần trên khoảng
   `2024-04-27 → 2026-09-02` với vốn 500 và đối chiếu với mốc đã biết ở đợt 37
   (`+123,02 USDT` cho tới `2026-09-08`). Giá trị tới `2026-09-02` sẽ **khác** vì ngắn hơn 6
   ngày — nêu cả hai con số và chênh lệch, đừng cố ép cho bằng.
3. `universe_tb` của tập OOS phải là **20**; của tập IS phải nằm giữa 10 và 18. Con số ngoài
   khoảng đó nghĩa là điều kiện đủ tư cách sai.

---

## Task 3 — Chạy đo, và luật chống dò tham số

**Bước CUỐI CÙNG.** Không sửa code sau khi bắt đầu.

### 3.1. Thứ tự — không đảo

| # | Lượt | Mục đích |
|---|---|---|
| 1 | `--split is` (baseline: lookback 30, rebalance 7, k 3, skip 0) | kết quả chính IS |
| 2 | `--split is --lookback 60` | độ nhạy |
| 3 | `--split is --lookback 90` | độ nhạy |
| 4 | `--split is --skip-recent 1` | biến thể động lượng cổ điển |
| 5 | `--split is --slippage-bps 2.0` | độ nhạy chi phí |
| 6 | **`--split oos`** — **chỉ baseline**, một lần duy nhất | kết luận |

**Lượt 6 chạy baseline và chỉ baseline.** Không chạy OOS cho các biến thể. Nếu lookback 60
đẹp hơn trên IS, đó **không** phải lý do đổi baseline — đó là lý do ghi vào mục "bề mặt tham
số" và để nguyên.

Lý do: chạy sáu biến thể qua OOS rồi lấy cái tốt nhất là dò tham số trá hình, và nó sẽ tạo ra
một kết quả dương giả mà không phép kiểm nào cứu được.

### 3.2. Bề mặt tham số — đọc hình dạng, không đọc đỉnh

Với bốn lượt độ nhạy (2–5), câu hỏi **không** phải "cái nào lãi nhất" mà là **"kết quả có ổn
định quanh baseline không"**. Ghi một dòng kết luận:

- Bốn biến thể cùng dấu và cùng bậc độ lớn → bề mặt **phẳng**, tham số không mong manh.
- Một biến thể dương còn lại âm → bề mặt có **đỉnh hẹp**, gần như chắc chắn là nhiễu.

### 3.3. Tiêu chí — chốt TRƯỚC khi xem kết quả

Chiến lược **đáng nghiên cứu tiếp** khi và chỉ khi **cả ba** đúng trên OOS:

1. `net_pnl > 0` sau phí, **và**
2. `rebalances >= 20`, **và**
3. kết quả thật nằm **trên phân vị 95** của phân phối null danh mục ngẫu nhiên.

Thiếu một điều → **kết quả âm**. Ghi nhận, không chỉnh tham số để cứu.

**Vượt hai mốc mua-và-giữ là mốc riêng, cao hơn**, báo cáo tách bạch. Một chiến lược trung
tính lãi ít hơn mua-và-giữ vẫn có thể đáng giá vì nó không phụ thuộc hướng thị trường — nhưng
đó là lập luận về rủi ro, không phải về lợi nhuận, và phải nói đúng như vậy.

### 3.4. File kết quả

`docs/superpowers/research/2026-09-12-dot-39-cat-ngang-20-ma.md` — **file mới, không ghi đè
file nào**.

1. Nguyên văn output cả sáu lượt, copy từ terminal.
2. Bảng tổng hợp IS/OOS, kèm cột phân vị null và hai cột mua-và-giữ.
3. Kết luận theo §3.3, một dòng.
4. Nhận định bề mặt tham số theo §3.2.
5. Mục **"Điều phép đo này KHÔNG trả lời"** — tối thiểu: thiên lệch sống sót, funding chưa
   tính, chưa mô phỏng thanh khoản từng mã (rổ chia đều giả định vào/ra được ở giá close mọi
   mã, kể cả mã nhỏ), chỉ một sàn BingX, chưa walk-forward.

---

## 4. Báo cáo cho Claude

1. `gitnexus_detect_changes()` (hoặc ghi rõ MCP timeout).
2. `git diff --stat` và `git status --short`.
3. Task 1: kết quả 11 test. Task 2: kết quả 3 tiêu chí, **kèm con số `universe_tb` thật** của
   cả hai tập.
4. Task 3: bảng tổng hợp, kết luận §3.3, nhận định bề mặt tham số §3.2.
5. Ba dòng: số test pass (mốc **697**), ruff, cổng cứng VN đủ bốn con số.
6. Đường dẫn file nghiên cứu mới.

Task nào chưa làm ghi thẳng **"CHƯA LÀM"** kèm lý do. **Không commit, không push.**

---

## 5. Điều KHÔNG thuộc phạm vi

- **Không** chạy khung 1H. Đã giải thích ở §2.1.
- **Không** thêm bộ lọc biến động, bộ lọc thanh khoản, trọng số theo vốn hoá, hay chuẩn hoá
  rủi ro. Baseline chia đều là baseline. Mọi thứ đó là đợt sau, **nếu** đợt này cho tín hiệu.
- **Không** đụng hai module một-mã của đợt 37, không sửa công cụ của đợt 38.
- **Không** nạp dữ liệu Binance, không mở module C/D của tài liệu gốc.
- **Không** dùng dữ liệu sau `2026-09-02`. Xem §0.2.
- **Không** dò lưới tham số. Bốn lượt độ nhạy ở §3.1 là để đọc hình dạng bề mặt, không phải
  để chọn cái tốt nhất.
- Ba câu hỏi lớn của đường VN vẫn là quyết định của chủ dự án, không phải việc của agent.
