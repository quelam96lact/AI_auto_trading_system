# Brief đợt 122 — tách thư viện đo cổ phiếu ra khỏi `screen_vcp_daily.py`, KHÔNG đổi một con số nào

**Base commit:** `39a7e40`.
**Người thực thi:** agent. **Người audit + commit + push:** Claude.
**Nguồn gốc việc này:** §1.1 và §A.6 của `docs/superpowers/research/2026-09-28-dot-120-do-diem-sepa.md`.

---

## §0. Việc này là gì, và thước đo thành công duy nhất

`scripts/screen_vcp_daily.py` (843 dòng) là script đo của đợt 99, nhưng đã thành **thư viện ngầm**: bốn script khác import từ nó, và một chuỗi script→script thứ hai (`measure_sepa_score_edge` import `calculate_rs_ranks` từ `score_sepa_daily`). Sửa một dòng ở đó có thể làm đổi âm thầm kết quả của năm phép đo.

Đợt này dời các hàm **trung tính** (không chứa lựa chọn của riêng đợt đo nào) sang **một module mới trong `trading/`**, và bắt nơi gọi truyền **tường minh** các hằng số tiền đăng ký của chính nó.

**Thước đo thành công duy nhất: năm script cho ra đầu ra y hệt từng ký tự trước và sau khi sửa** (trừ các dòng đo thời gian chạy). Đây là refactor thuần. Đầu ra đổi dù chỉ một chữ số là **thất bại**, kể cả khi con số mới "trông đúng hơn".

---

## §1. Đính chính của tôi trước khi giao việc — đọc kỹ

### §1.1. Cặp hàm tôi từng gọi là "cùng logic" KHÔNG giống nhau

Ở §A.8 báo cáo đợt 120 tôi ghi `basket_baseline` / `baseline_for_basket` và `excess_for_event` / `excess_k` là "cùng logic, hai tên khác nhau", và đề nghị gộp chúng. **Sai.** Đọc kỹ thì thấy:

| | `screen_vcp_daily.py` (đợt 99) | `screen_smc_stock_daily.py` (đợt 101) |
|---|---|---|
| Kiểu phần tử rổ | `ControlEntry` — ba trường cố định `r5`, `r10`, `r20` | `BasketEntry` — `dict` theo k |
| `TARGET_KS` | (5, 10, 20) | (10, 20, **40**) — `ControlEntry` không chứa nổi k = 40 |
| Rổ không có giá trị nào thì trả | `(None, len(entries))` | `(None, 0)` |
| `IS_SIGNAL_END` | 2022-11-30 | 2022-10-31 |

**Hệ quả cho đợt này: KHÔNG gộp các hàm rổ đối chứng.** Gộp chúng là một quyết định thiết kế (chọn kiểu phần tử rổ nào, xử lý rổ rỗng ra sao), không phải một phép dời. Việc đó đi cùng đợt đo lại SEPA với mốc trung tính, nơi nó thật sự cần.

### §1.2. Hằng số KHÔNG phải "giao thức chung" — mỗi đợt tự tiền đăng ký bộ của mình

Bảng trên cho thấy đợt 101 tự khai lại gần hết hằng số, có cái trùng giá trị với đợt 99 và có cái khác. Nên **không được** dời hằng số tiền đăng ký của đợt 99 sang thư viện rồi gọi đó là "giao thức" — làm vậy là trói ngầm mọi đợt đo sau vào lựa chọn của đợt 99, đúng kiểu lỗi đã làm hỏng đợt 120 (một lựa chọn chôn bên trong hàm thay vì nằm ở chỗ gọi).

Quy tắc: thư viện chỉ chứa **sự thật** (luật sàn, định nghĩa Trend Template, mốc niêm phong cổ phiếu). Còn **lựa chọn** (cửa sổ In-Sample, k mục tiêu, số lần bootstrap, seed, ngưỡng thanh khoản, số nến nghỉ, khoảng tin cậy) nằm ở từng đợt đo.

### §1.3. Gộp mốc niêm phong forex/crypto: dời sang đợt sau

Sau audit đợt 121 tôi nói sẽ đưa việc gộp mốc niêm phong 2026-08-31 (lặp ở khoảng bảy file forex/crypto) vào brief này. **Tôi đổi ý:** đó là bảy file ở một mảng khác (forex/crypto), với bốn cách biểu diễn khác nhau (chuỗi timestamp, chuỗi ngày, `date`, mili-giây `int`), và mỗi bản hiện đều đúng. Gộp vào đây sẽ nhân đôi phạm vi, và nếu đầu ra đổi thì không biết lỗi nằm ở phần nào. Việc đó thành một đợt nhỏ riêng.

---

## §2. Phạm vi phẫu thuật

### §2.1. Tạo mới

- `trading/stock_study.py` — thư viện. Đặt tên theo kiểu module phẳng sẵn có của `trading/` (`metrics.py`, `sampling.py`, `data_quality.py`).
- `tests/test_stock_study.py` — **chỉ khi** cần chỗ cho test của hàm đã dời; ưu tiên sửa import ở test cũ hơn là chuyển test.

### §2.2. DỜI sang `trading/stock_study.py` — đúng danh sách này, không hơn không kém

**Sự thật (hằng số dời theo):**

| Tên | Vì sao là sự thật |
|---|---|
| `SEALED_START` | mốc niêm phong cổ phiếu 2023-01-01 của cả dự án |
| `LIMIT_BY_EXCHANGE`, `DEFAULT_LIMIT_RATE`, `LIMIT_EPS` | luật biên độ của sàn |
| `TREND_KEYS`, `TREND_MIN_BARS`, `RANGE_WINDOW` | định nghĩa Trend Template (252 nến = đỉnh/đáy 52 tuần) |

**Hàm:**

| Nhóm | Hàm |
|---|---|
| Thời gian, dữ liệu | `bar_date`, `month_key`, `validate_sealed_bars`, `clean_bars`, `load_universe` |
| Chỉ báo | `rolling_mean`, `rolling_max`, `rolling_min`, `_trend_from_arrays`, `_all_false`, `trend_conditions` |
| Cơ chế thị trường VN | `limit_rate`, `is_ceiling_open`, `entry_status`, `net_return`, `compute_targets`, `liquidity_ok`, `apply_cooldown` |
| Thống kê | `bootstrap_by_month`, `_percentile` (xem §4 Bước 2 — sẽ bị thay) |
| Từ `score_sepa_daily.py` | `calculate_rs_ranks` |

### §2.3. Tham số mặc định mang lựa chọn của đợt 99 → thành tham số BẮT BUỘC

Khi dời, các tham số dưới đây **bỏ giá trị mặc định** và trở thành keyword bắt buộc:

| Hàm | Tham số hết mặc định |
|---|---|
| `liquidity_ok` | `window`, `min_turnover` |
| `apply_cooldown` | `cooldown` |
| `compute_targets` | `ks` |
| `bootstrap_by_month` | `n`, `seed`, và **thêm** `ci_low_pct`, `ci_high_pct` (hiện đang đọc thẳng `CI_LOW_PCT` / `CI_HIGH_PCT` bên trong hàm) |

Ở **mọi** nơi gọi, truyền tường minh hằng số của **chính đợt đo đó**. Giá trị truyền vào phải **bằng đúng** giá trị mà mặc định cũ đã cho — đầu ra y hệt ở §5 là bằng chứng.

Nếu một đợt đo đang ngầm dựa vào mặc định của đợt 99 mà chưa tự khai hằng số tương ứng (ví dụ đợt 101 gọi `bootstrap_by_month` nhưng không có `CI_LOW_PCT`), **khai hằng số đó trong script của đợt ấy**, kèm chú thích nguồn gốc theo đúng kiểu `screen_smc_stock_daily.py` đang dùng:

```python
MIN_TURNOVER_VND = 1_000_000_000.0           # 1 ty dong, y het dot 99
```

Không thêm giá trị mặc định mới cho bất kỳ tham số nào khác.

Hai chỗ tôi đã thấy trước ở `screen_smc_stock_daily.py` (đợt 101), để bạn biết §2.3 đang nhắm vào cái gì — **không** phải danh sách đầy đủ, bạn phải tự rà hết:

- Dòng 154 và 232 gọi `liquidity_ok(..., min_turnover=min_turnover)` mà **không** truyền `window`, tức đang dựa ngầm vào `TURNOVER_WINDOW` của đợt 99. Đợt 101 không tự khai hằng này.
- Dòng 430 gọi `bootstrap_by_month(..., n=..., seed=...)`, nhưng khoảng tin cậy 2,5 / 97,5 lấy ngầm từ `CI_LOW_PCT` / `CI_HIGH_PCT` của đợt 99. Đợt 101 cũng không tự khai.

Đó chính là kiểu phụ thuộc ngầm mà đợt này phải làm lộ ra.

### §2.4. GIỮ LẠI trong `screen_vcp_daily.py`

Mọi hằng số tiền đăng ký của đợt 99 (`IS_SIGNAL_START`, `IS_SIGNAL_END`, `READ_FROM`, `READ_TO`, `MIN_TURNOVER_VND`, `TURNOVER_WINDOW`, `COOLDOWN_BARS`, `TARGET_KS`, `MAIN_K`, `MIN_CONTROL`, `N_BOOTSTRAP`, `BOOTSTRAP_SEED`, `MIN_EVENTS`, `CI_LOW_PCT`, `CI_HIGH_PCT`, `BASE_LEN`, `SEG_LEN`, `BREAKOUT_*`), `in_is`, toàn bộ phần dò VCP (`base_depths`, `pivot_price`, `vcp_base_ok`, `breakout_ok`, `trend_filter_ok`, `find_events`), **toàn bộ máy rổ đối chứng** (`ControlEntry`, `_r_of`, `basket_baseline`, `excess_for_event`, `SymbolData`, `compact_control_series`), `Event`, `_describe`, `run_screen`, phần báo cáo và `main`.

### §2.5. Một ngoại lệ được chấp nhận có chủ đích

Sau đợt này `measure_sepa_score_edge.py` **vẫn** import từ `screen_vcp_daily.py`: hằng số của đợt 99, `in_is`, máy rổ đối chứng và `_describe`. Đó là thiết kế của đợt 120 — nó tiền đăng ký "dùng lại nguyên máy đo của đợt 99". Mối nối này sẽ bị xoá khi đợt đo lại SEPA thay rổ. **Không** cắt nó trong đợt này, **không** chép máy rổ sang script khác.

Mọi script khác (`score_sepa_daily`, `screen_smc_stock_daily`, `screen_momentum_portfolio`) sau đợt này phải **không còn** import gì từ `screen_vcp_daily`; `measure_sepa_score_edge` phải **không còn** import gì từ `score_sepa_daily`.

### §2.6. KHÔNG được đụng

- `screen_smc_stock_daily.py`: `BasketEntry`, `make_basket_entry`, `basket_for_day`, `baseline_for_basket`, `excess_k`, `median_of` — **giữ nguyên**, lý do ở §1.1. Chỉ được đổi dòng import và truyền tham số tường minh theo §2.3.
- `score_sepa_daily.py::load_untrusted_symbols` — **không dời**. Hai test đang `monkeypatch` nó trên module `score_sepa_daily` (`tests/test_score_sepa_daily.py:249` và `:287`); dời nó thì patch sẽ rơi vào khoảng không và test xanh mà không kiểm gì.
- `load_universe`: dời **nguyên trạng**. Nó có một bẫy đã biết: `pathlib.Path("").exists()` trả `True` trên Windows (agent đợt 120 đã né bằng tên file giả `__no_exclusions__.tmp`). **Không sửa** bẫy đó trong đợt này — sửa thì đổi hành vi. Chỉ báo lại.
- Hai hàm phân vị thang **0–1** trong `check_bingx_tracking.py` và `measure_forex_perp_cost.py` — khác quy ước, ngoài phạm vi.
- `trading/metrics.py` — chỉ được **import** `calculate_percentile`, không được sửa.
- Mọi file forex/crypto, mọi file `trading/` khác ngoài module mới, `exclusions.txt`, `.env`, `docker-compose.yml`.
- **Mọi đầu ra đã commit** trong `docs/superpowers/research/dot-*-output/`. Xem cảnh báo ở §3.

### §2.7. Quy tắc truy vết

Mọi dòng thay đổi phải thuộc một trong bốn loại: (a) dời nguyên văn, (b) đổi import, (c) truyền tham số tường minh theo §2.3 hoặc khai hằng số kèm chú thích nguồn gốc, (d) Bước 2 ở §4. Được sửa định dạng **chỉ** khi `ruff check trading` đòi (vì code dời vào `trading/` giờ chịu ruff), và phải liệt kê từng chỗ. **Không** đổi tên, **không** đổi logic, **không** "tiện thể" dọn dẹp.

---

## §3. Bước 0 — chụp "đầu ra vàng" TRƯỚC khi sửa một dòng nào

Chạy năm lệnh dưới đây trên code gốc (`39a7e40`), lưu stdout (và file ghi ra) vào một thư mục **ngoài repo**, ví dụ `D:\My_Vault_Obsidian\Project\_backups\dot122_golden\truoc\`.

```
uv run python scripts/screen_vcp_daily.py
uv run python scripts/screen_smc_stock_daily.py
uv run python scripts/screen_momentum_portfolio.py
uv run python scripts/score_sepa_daily.py --as-of 2026-09-25 --output <thu_muc_ngoai_repo>\score_sepa_20260925.txt
uv run python scripts/measure_sepa_score_edge.py --output-dir <thu_muc_ngoai_repo>\dot120
```

**Cảnh báo — `measure_sepa_score_edge.py` mặc định GHI ĐÈ vào `docs/superpowers/research/dot-120-output/`**, tức đầu ra đã commit của đợt 120. **Bắt buộc** truyền `--output-dir` ra ngoài repo. Sau mỗi lần chạy, `git status` phải cho thấy thư mục `dot-120-output` **không** đổi.

`--as-of 2026-09-25` là ngày của đầu ra đợt 119 đã commit. Kiểm trước rằng đó là một phiên giao dịch có dữ liệu.

**Ghi PowerShell:** `>` ghi UTF-16 và sẽ làm mọi phép so hỏng. Dùng `uv run python ... | Out-File -Encoding utf8 <file>`, hoặc để script tự ghi qua `--output` / `--output-dir`.

### §3.1. So với đầu ra đã commit — hai mốc độc lập

Hai script có đầu ra đã commit, **không phải** con số tôi gõ vào brief:

| Script | Mốc độc lập |
|---|---|
| `score_sepa_daily.py --as-of 2026-09-25` | `docs/superpowers/research/dot-119-output/full_universe_scorecard_20260925.txt` |
| `measure_sepa_score_edge.py` | `docs/superpowers/research/dot-120-output/full_run_output_with_exclusions.txt` và `summary_table_with_exclusions.txt` |

So lần chạy "trước" của bạn với hai mốc này **và báo cả khi chúng lệch**. Lệch ở bước này **không phải lỗi refactor** — code chưa bị sửa. Nó có thể là trôi dữ liệu (collector UPSERT lại nến ngày cũ) hoặc là mốc đợt 119 không được sinh bằng đúng lệnh này. Báo nguyên văn phần lệch, **đừng** tự giải thích thay tôi, và **đừng** dừng — mốc thật của đợt này là lần chạy "trước" của chính bạn.

---

## §4. Các bước — mỗi bước một cổng kiểm

```
Bước 1. Dời theo §2.2, bỏ mặc định theo §2.3, đổi import ở năm script và năm file
        test (test_screen_vcp_daily, test_screen_smc_stock_daily,
        test_screen_momentum_portfolio, test_score_sepa_daily,
        test_measure_sepa_score_edge).
        → Kiểm bằng: chạy lại năm lệnh ở §3 vào thư mục `sau_buoc1\`, rồi so với
          `truoc\`. PHẢI y hệt từng ký tự, trừ các dòng in thời gian chạy
          (nguồn: time.perf_counter). Liệt kê chính xác từng dòng bị loại khỏi phép
          so và vì sao.
        → Và: uv run pytest -q   (TOÀN BỘ suite, GỒM integration — xem §4.1)
        → Và: uv run ruff check trading tests

Bước 2. Thay `_percentile` bằng `trading.metrics.calculate_percentile` ở HAI chỗ:
        bản đã dời vào trading/stock_study.py (dùng trong bootstrap_by_month) và
        bản sao riêng trong screen_momentum_portfolio.py. Sau đó xoá hai bản
        `_percentile` đã hết người dùng.
        → Kiểm bằng: y như Bước 1, vào thư mục `sau_buoc2\`, so với `truoc\`.

Bước 3. Kiểm ranh giới import bằng grep:
        - score_sepa_daily, screen_smc_stock_daily, screen_momentum_portfolio:
          KHÔNG còn dòng nào import từ screen_vcp_daily.
        - measure_sepa_score_edge: KHÔNG còn import từ score_sepa_daily; chỉ còn
          import từ screen_vcp_daily đúng các tên liệt kê ở §2.5.
        → Nộp output grep nguyên văn.
```

### §4.1. Vì sao phải chạy TOÀN BỘ suite, không chỉ `-m "not integration"`

Ở đợt 121, cả năm test của đường tiền thật đều bị `deselected` dưới `-m "not integration"`, vì marker đặt ở mức module. Con số "1.253 passed" khi đó không chạy test nào của phần quan trọng nhất. Lần này hạ tầng test đã sẵn (`docker compose --profile test up -d nats-test`, DB `trading_test`). Chạy `uv run pytest -q` **không lọc marker**. Mốc hiện tại là **1.396 passed**; sau đợt này phải **≥ 1.396, 0 failed**.

### §4.2. Về Bước 2 — một khác biệt nhỏ cần biết trước

Hai hàm phân vị cho cùng kết quả trên danh sách không rỗng, **nhưng** thứ tự phép tính khác nhau: `_percentile` tính `(n-1) * pct / 100`, còn `calculate_percentile` tính `(p / 100) * (n-1)`. Với số thực dấu phẩy động, hai cách này có thể lệch ở chữ số cuối cùng (cỡ 1e-15). Tôi dự đoán lệch đó **không** hiện ra ở đầu ra in (khoảng tin cậy được in 2–4 chữ số thập phân), nhưng **tôi chưa kiểm**.

- Nếu đầu ra sau Bước 2 y hệt: tốt.
- Nếu lệch **chỉ** ở chữ số cuối của khoảng tin cậy: **dừng Bước 2, hoàn nguyên nó, giữ kết quả Bước 1**, và báo lại nguyên văn các dòng lệch. **Không** được "sửa" bằng cách làm tròn, đổi định dạng in, hay viết lại `calculate_percentile`. Việc đó để tôi quyết.

Lý do làm Bước 2: `_percentile` trả `0.0` khi danh sách rỗng — đúng lớp lỗi đã sửa trong `trading/metrics.py` ở commit `d49ca96`. Dời nguyên nó vào `trading/` sẽ tạo **hai** hàm phân vị trong cùng package, một hàm mang lỗi cũ.

---

## §5. Tiêu chí hoàn thành

1. Ba bộ đầu ra `truoc\`, `sau_buoc1\`, `sau_buoc2\` (hoặc `sau_buoc1\` và báo cáo dừng Bước 2 theo §4.2), kèm lệnh so và output của lệnh so.
2. Bảng so `truoc\` với hai mốc độc lập ở §3.1.
3. `uv run pytest -q` (không lọc marker): ≥ 1.396 passed, 0 failed, output nguyên văn.
4. `uv run ruff check trading tests`: sạch.
5. Output grep của Bước 3.
6. `git status` chứng minh `docs/superpowers/research/dot-*-output/` không đổi.
7. Diff đầy đủ, và một bảng ánh xạ **từng hàm/hằng đã dời**: dòng cũ trong `screen_vcp_daily.py` → dòng mới trong `trading/stock_study.py`.
8. Danh sách **mọi** chỗ truyền tham số tường minh theo §2.3 và mọi hằng số mới khai theo §2.3, mỗi chỗ kèm giá trị và nguồn gốc của giá trị đó.

---

## §6. Ba phép phá thử bắt buộc

Mục đích: chứng minh cổng "đầu ra y hệt" thật sự bắt được thay đổi hành vi, không phải lúc nào cũng xanh. Mỗi phép: sửa **một** chỗ trên bản đã refactor, chạy lại **một** script liên quan (được dùng `--limit` để nhanh, nhưng khi đó phải so với một lần chạy `--limit` cùng giá trị trên bản chưa phá), xác nhận đầu ra **lệch**, rồi phục hồi và xác nhận đầu ra trở lại y hệt.

| # | Đột biến | Script dùng để phát hiện |
|---|---|---|
| 1 | Ở **một** chỗ gọi `liquidity_ok` trong `screen_smc_stock_daily.py`, truyền `min_turnover` bằng 0,9 lần giá trị đúng | `screen_smc_stock_daily.py` |
| 2 | Trong `bootstrap_by_month`, đổi `seed` thành `seed + 1` | `screen_vcp_daily.py` |
| 3 | Trong `trading/stock_study.py`, đổi `LIMIT_EPS` từ `0.001` thành `0.002` | `screen_momentum_portfolio.py` |

Nếu một đột biến **không** làm lệch đầu ra (ví dụ vì `--limit` quá nhỏ nên không phiên nào rơi vào dải bị đổi), phép phá thử đó là **chưa kết luận được**, không phải đạt. Tăng `--limit` hoặc chạy đủ, rồi báo cả hai lần. **Không** được đổi đột biến sang một thứ khác cho dễ lệch mà không nói.

**Kinh nghiệm từ các đợt trước** (tôi từng tự làm hỏng phép phá thử của chính mình ba lần):
- File trong repo có thể là **CRLF**. Thay chuỗi bằng pattern LF sẽ **không khớp**, đột biến **không được áp**, và cổng xanh giả. Sau mỗi lần sửa, in `changed=True` và grep lại file.
- Phục hồi bằng bản sao lưu tạo **sau** khi refactor xong, không phải bản gốc.
- `Set-Content -Encoding utf8` chèn BOM. Dùng `[System.IO.File]::WriteAllText` với `UTF8Encoding($false)`.

---

## §7. Bằng chứng về GitNexus

- `gitnexus_impact` (hướng upstream) cho **mỗi** hàm ở §2.2 trước khi dời. MCP có thể không kết nối được (phiên của Claude bị `CONNECT_TIMEOUT` suốt). CLI thì chạy được, nhưng phải chỉ định repo vì máy có ba repo được index: `npx gitnexus <lệnh> --repo AI_auto_trading_system`. Nếu không gọi được, **nói rõ**, rồi thay bằng grep caller thủ công và báo blast radius.
- `npx gitnexus detect-changes --repo AI_auto_trading_system` sau khi xong, output nguyên văn.
- **Không** chạy `npx gitnexus analyze --force`.
- Refactor này sẽ báo rủi ro HIGH hoặc CRITICAL gần như chắc chắn (dời hàm có nhiều caller). Đó là dự kiến. Việc của bạn là **báo** mức rủi ro, không phải né nó. Cổng thật là §5 mục 1.

---

## §8. Điều cấm

- **Không commit, không push.** Claude làm việc đó sau khi audit.
- Không đặt, sửa, huỷ lệnh thật; không bật `real_trading_enabled`; **không chạy `--send`**.
- Không rebuild, không restart container. Module mới nằm trong `trading/` nên **Claude** sẽ rebuild sau khi commit.
- **Cấm `git checkout`, `git restore`, `git stash`.** Sao lưu đặt **ngoài** repo.
- Không đọc dữ liệu từ mốc niêm phong để **đo**: cổ phiếu từ 2023-01-01; VN30F từ 01/08/2026; crypto/BingX từ 2026-09-01. `score_sepa_daily.py` là công cụ **hiển thị** đợt 119 được phép đọc dữ liệu mới; nó không phải phép đo.
- **Không đổi bất kỳ hằng số tiền đăng ký nào.** Không đổi giá trị, không đổi tên.
- **Không ghi đè** bất kỳ file nào trong `docs/superpowers/research/dot-*-output/`.
- Không in giá trị biến môi trường; không đọc nội dung `.env`.
- Không sửa dead code có từ trước. Không "tiện thể" refactor.

---

## §9. Giả định của tôi — sai thì dừng và báo

1. **Năm script đều tất định** ngoài các dòng `time.perf_counter()`. Căn cứ: bootstrap dùng `random.Random(seed)` với seed cố định; grep không thấy `datetime.now`, `date.today`, `np.random`. Nếu hai lần chạy liên tiếp trên **cùng** code gốc mà khác nhau, **dừng ngay** — nghĩa là cổng của đợt này không dùng được, và phải báo tôi trước khi làm gì tiếp.
2. **Không có test nào patch thuộc tính của `screen_vcp_daily` hay của các hàm sẽ dời.** Căn cứ: grep `monkeypatch` và `mock.patch` trong năm file test chỉ thấy hai chỗ, đều patch `load_untrusted_symbols` (không dời). Nếu thấy chỗ khác, báo.
3. **`_percentile` và `calculate_percentile` cho cùng kết quả trên danh sách không rỗng**, trừ khả năng lệch ở chữ số cuối như §4.2.
4. **`bootstrap_by_month` không bao giờ nhận danh sách mẫu rỗng** khi được gọi từ năm script. Căn cứ: mảng `means` luôn có đúng `n ≥ 1` phần tử. Nếu sai, `calculate_percentile` sẽ `raise` ở Bước 2 — tức Bước 2 vừa làm lộ ra một chỗ mà bản cũ đã âm thầm in ra `0.0`. Báo lại, đừng che.
5. **Dời code vào `trading/` không làm engine đổi hành vi**, vì engine không import module mới. Nếu thấy `trading/engine` hay `trading/collector` có import gì từ các hàm sẽ dời, **dừng và báo**.
