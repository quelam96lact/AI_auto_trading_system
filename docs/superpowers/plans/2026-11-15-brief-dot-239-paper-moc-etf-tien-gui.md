# Brief đợt 239: chạy paper mốc ETF VN30 15% + tiền gửi 6% trên engine nến ngày

- **Ngày:** 15/11/2026. **Quyết định:** chủ dự án 15/11 chọn hướng 3 sau hai phép đo âm 237/238.
- **Không phải giả thuyết mới** (không dùng ngân sách mục F). Đây là mốc "không làm gì" đã đo ở đợt 165 (`scripts/measure_etf_deposit_mix.py`, memory `moc-chuan-etf-cong-tien-gui`): 15% `E1VFVN30`, phần còn lại gửi 6%/năm, tái cân bằng mỗi năm. Chạy paper để có đường chuẩn sống cho mọi chiến lược sau.
- **Builder** viết code + test, KHÔNG commit/push, KHÔNG docker, KHÔNG `sched.sh`, KHÔNG ghi DB `trading` thật (test DB chỉ `trading_test`), không `npx`, không `taskkill` theo tên, không đọc file bí mật.
- **Researcher** (song song, không xem code Builder) dựng kịch bản tính tay độc lập từ §2–§3.
- **Lead** audit, chạy kịch bản của Researcher, commit, push, đặt biến môi trường và deploy trước 21:45 thứ Hai 16/11 (sổ `paper_daily_state` hiện chưa có dòng nào, nên lần chạy đầu sẽ khởi tạo sổ với chiến lược này).

## 1. Phạm vi file

Được sửa: `trading/daily_engine/core.py`, `strategy.py`, `store.py`, `runner.py`; `trading/storage/schema.sql` (chỉ thêm cuối file); test `tests/test_daily_engine_core.py`, `tests/test_daily_engine_runner.py` (chỉ thêm), test mới `tests/test_daily_engine_etf_deposit.py`. **Không** sửa `docker-compose.yml` (Lead làm), `scripts/measure_etf_deposit_mix.py`, `scripts/heartbeat_check.py`, hay file nào khác. Hành vi với chiến lược `null` phải **không đổi** (mọi test đợt 233 vẫn xanh, không sửa assert cũ).

## 2. Lãi tiền gửi trên tiền mặt (mới)

- `core.py`: hàm thuần `accrue_cash_interest(cash: float, prev_date: date, d: date, annual_rate: float) -> float` trả **số tiền lãi**: `cash × ((1 + annual_rate) ** (days / 365) − 1)` với `days = (d − prev_date).days` (ngày lịch, đúng công thức đợt 165). Trả `0.0` khi `annual_rate == 0`, `days <= 0` hoặc `cash <= 0`.
- Mỗi chiến lược có thuộc tính `cash_rate: float` (lãi năm trên tiền mặt). `NullDailyStrategy.cash_rate = 0.0`.
- `runner.py`, với mỗi phiên `d`, **trước** `process_day`: `interest = accrue_cash_interest(state.cash, state.last_processed_date, d, strategy.cash_rate)`; `cash += interest`; `realized_pnl += interest` (để bất biến sổ `cash + Σ giá vốn − capital == realized_pnl` của heartbeat vẫn đúng). Sau đó mới `process_day` (khớp lệnh ở open `d`), định giá, rồi `on_day`.
- `paper_daily_nav` thêm cột `interest double precision NOT NULL DEFAULT 0` (lãi cộng trong ngày `d`): thêm cuối `schema.sql` bằng `ALTER TABLE paper_daily_nav ADD COLUMN IF NOT EXISTS ...` (bảng đã tồn tại trên DB thật).
- Chạy lại cùng ngày không cộng lãi lần hai; `--dry-run` không để lại gì.

## 3. Chiến lược `EtfDepositStrategy` (`strategy.py`)

- `name = "etf_deposit"`, đăng ký trong `STRATEGIES`. Hằng: `ETF_SYMBOL = "E1VFVN30"`, `ETF_WEIGHT = 0.15`, `cash_rate = 0.06`. Một test khẳng định ba hằng này **bằng** `SYMBOL`, `MAIN_WEIGHT`, `MAIN_RATE` của `scripts/measure_etf_deposit_mix.py` (không import từ `scripts/` trong code sản phẩm).
- `DailyContext` thêm trường `next_trading_day: date | None = None` (tham số cuối, mặc định `None`). Runner điền phiên giao dịch kế tiếp sau `d` theo `is_trading_day` + holidays của config (không cần có dữ liệu của ngày đó).
- `on_day(ctx)`:
  1. `bar = ctx.bars(ETF_SYMBOL, 1)`; không có nến, hoặc nến cuối không đúng ngày `ctx.d`, hoặc `close <= 0` → trả `[]`.
  2. `target = floor(ETF_WEIGHT × ctx.nav / close / 100) × 100`; `pos = ctx.positions.get(ETF_SYMBOL, 0)`.
  3. **Mua lần đầu:** `pos == 0` và `target > 0` → `[OrderIntent(ETF_SYMBOL, "BUY", target)]`.
  4. **Tái cân bằng năm:** `pos > 0`, `ctx.next_trading_day` khác `None` và `ctx.next_trading_day.year > ctx.d.year` (tức `d` là phiên cuối năm; lệnh khớp ở open phiên đầu năm sau, đúng quy tắc đợt 165): `diff = target − pos`; `diff >= 100` → BUY `diff`; `diff <= −100` → SELL `−diff`; còn lại `[]`.
  5. Mọi trường hợp khác → `[]`. Chiến lược không giữ trạng thái riêng.
- Lệch có chủ đích so với mô phỏng đợt 165 (ghi trong docstring): khối lượng làm tròn lô 100; lần mua đầu chia theo close phiên quyết định, khớp ở open phiên sau; lệnh hết hạn (không có nến) thì lần mua đầu tự đặt lại ở phiên sau vì `pos` vẫn 0, còn lệnh tái cân bằng thì bỏ qua năm đó.

## 4. Test (TDD, đỏ trước)

Phép phá (sao lưu ngoài repo; cấm `git checkout/restore/stash`), mỗi phép làm đỏ một test gọi đúng hàm sản phẩm:

| # | Phép phá | Hàm |
|---|---|---|
| a | Lãi tính đơn (`cash × r × days/365`) hoặc theo 252 phiên | `accrue_cash_interest`, so số **tính tay** |
| b | Lãi không cộng vào `realized_pnl` | runner (integration): bất biến sổ lệch |
| c | Chạy lại cùng ngày cộng lãi lần hai | runner (integration) |
| d | Chiến lược `null` cũng được cộng lãi | runner (integration) |
| e | Lãi cộng **sau** khi khớp lệnh thay vì trước | runner (integration), so tiền mặt tính tay ở ngày có lệnh mua |
| f | `target` tính theo `cash` thay vì `nav`, hoặc không làm tròn xuống lô 100 | `EtfDepositStrategy.on_day` |
| g | Tái cân bằng mỗi ngày, hoặc không bao giờ | `on_day` (một ngày giữa năm và một ngày cuối năm) |
| h | Đặt lệnh khi nến ETF không đúng ngày `d` | `on_day` |
| i | Thừa tỷ trọng mà đặt BUY (sai dấu), hoặc lệch dưới 100 cp vẫn đặt lệnh | `on_day` |
| j | Runner không điền `next_trading_day`, hoặc điền chính `d` | runner (integration) |
| k | `--dry-run` để lại lãi/lệnh trong DB | runner (integration) |

Thêm một test integration đi qua **cuối năm**: dữ liệu tổng hợp 6 phiên (4 phiên cuối tháng 12, 2 phiên đầu tháng 1), sổ khởi tạo trước phiên đầu; so `paper_daily_nav` (`cash`, `market_value`, `nav`, `interest`) từng ngày với số **tính tay** ghi trong test: ngày 1 đặt mua, ngày 2 khớp, cuối năm đặt tái cân bằng, phiên đầu năm khớp.

## 5. Tiêu chí hoàn thành (dán output thật)

1. Impact/grep trước khi sửa `process_day`/runner (`node .gitnexus/run.cjs impact ... --repo .`, bổ sung grep).
2. Test mới đỏ trước, xanh sau; bảng phá a–k với dòng `FAILED` nguyên văn.
3. `uv run ruff check trading tests scripts`; `uv run pytest -m "not integration" -q`; `uv run pytest -m integration -q tests/test_daily_engine_runner.py tests/test_daily_engine_etf_deposit.py` (DB test).
4. `detect-changes --scope all`; `git status --short`; `git diff --stat`.
5. Một câu: "Tôi không chạy docker, không ghi DB thật, không sửa file ngoài §1."
6. Mọi chỗ brief mơ hồ mà Builder phải tự diễn giải.
