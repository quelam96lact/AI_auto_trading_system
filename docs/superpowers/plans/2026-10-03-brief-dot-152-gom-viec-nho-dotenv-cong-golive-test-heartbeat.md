# Brief đợt 152 — ba việc nhỏ: nạp `.env` một chỗ, cổng go-live không đỏ giả, test heartbeat không gắn cứng tài khoản

Chủ dự án chọn "gom việc nhỏ" ngày 03/10. Cả ba việc đều không đổi hành vi của engine/collector.

## Việc 1 — cổng go-live đỏ giả mục Telegram khi chạy với `--dsn`

Claude đo ngày 03/10 lúc 07:34:
- `uv run python scripts/check_golive_gate.py --dsn postgresql://...@127.0.0.1:5432/trading` → mục 7
  `THIẾU BIẾN MÔI TRƯỜNG ... [CHẶN]`.
- Cùng lệnh **bỏ `--dsn`** → mục 7 `ĐÃ CẤU HÌNH [ĐẠT]`.

Nguyên nhân: `scripts/_db_common.py::resolve_dsn` chỉ gọi `load_dotenv()` khi **không** có `override`.
`check_golive_gate.py::check_telegram_configured` đọc `os.environ`, nên có `--dsn` thì `.env` không được
nạp và mục Telegram báo CHẶN dù cấu hình đúng. Đây là cổng quyết định có bật tiền thật hay không, nên một
dòng đỏ giả cũng đáng sửa. Đỏ giả quen mắt rồi thì đỏ thật cũng bị bỏ qua.

**Sửa:** trong `check_golive_gate.py::main`, gọi `load_dotenv()` của `_db_common` **vô điều kiện**, trước
`resolve_dsn`. Theo đúng khuôn import `try: from _db_common ... except ImportError: from
scripts._db_common ...` đã có trong `main`. **Không** sửa `resolve_dsn`: 66 file trong `scripts/` import `_db_common`, và hành vi
"có `--dsn` thì không nạp DSN từ `.env`" là đúng cho DSN.

→ kiểm chứng bằng: test trong `tests/test_check_golive_gate.py`:
- monkeypatch hàm nạp `.env` thành một spy, và `run_gate_check` thành stub trả 0;
- gọi `main` với `--dsn x`;
- khẳng định spy **được gọi**.

Phá thử: chuyển lời gọi vào trong nhánh `if not args.dsn` → test đỏ. Chạy thật cả hai dạng lệnh (có và
không `--dsn`) và dán dòng mục 7 của mỗi lần. Hai dòng phải giống nhau. Mục 8 (deploy-drift) sẽ CHẶN cho
tới khi Claude build lại image; đó là đúng, không phải việc của agent.

## Việc 2 — gom sáu bản sao `_load_dotenv` về `_db_common.load_dotenv`

Sáu file định nghĩa cùng một hàm `_load_dotenv(env_path=".env")`, giống hệt nhau từng dòng:

```
scripts/build_derivative_continuous_series.py   scripts/check_orderbook_daily.py
scripts/probe_account_balance_22h.py            scripts/record_vn30f_orderbook.py
scripts/screen_vn30f_intraday.py                scripts/verify_orderbook_file.py
```

`scripts/_db_common.py::load_dotenv()` làm cùng việc (`setdefault`, bỏ dòng trống/`#`, tách ở dấu `=` đầu
tiên). Chỉ khác ở một điểm: bản dùng chung đọc `.env` ở **gốc repo**, còn bản sao đọc `.env` theo **thư mục
đang đứng** (cwd). Mọi job theo lịch chạy với cwd = gốc repo, nên kết quả như nhau. Chạy tay từ thư mục khác
thì bản dùng chung đúng hơn.

**Sửa**, trong mỗi file:
- xoá `def _load_dotenv`;
- thay bằng `from _db_common import load_dotenv as _load_dotenv`, theo khuôn try/except ImportError của
  chính file đó; nếu file chưa có khuôn thì theo khuôn trong `check_golive_gate.py::main`.

**Giữ tên `_load_dotenv` trong module.** `tests/test_collector_logging.py:87` monkeypatch
`record_vn30f_orderbook._load_dotenv`; mất tên đó thì test vỡ. Không đổi call site nào. Không ai truyền
`env_path`; Claude đã grep, cả sáu chỗ gọi đều là `_load_dotenv()`. Import `os` nào chỉ còn thừa vì việc này
thì xoá; import có từ trước thì không đụng.

→ kiểm chứng bằng:
- `grep -rn "def _load_dotenv" scripts` ra **0 dòng**;
- một script nhỏ (không commit) import cả sáu module dưới dạng `scripts.<tên>` và in
  `mod._load_dotenv is scripts._db_common.load_dotenv`. Phải ra `True` ×6;
- `tests/test_collector_logging.py` xanh.

## Việc 3 — test heartbeat gắn cứng số tài khoản

Đợt 150 đổi ba assert trong `tests/test_heartbeat_check.py` (khoảng dòng 516, 529, 548) từ `"0434221"`
sang `"0434226"`. Các test này chạy `heartbeat_check.main`, mà `main` đọc **config thật**
`config/config.yaml`. Lần đổi tài khoản tới, chúng lại vỡ.

**Sửa:** ba assert lấy số tài khoản kỳ vọng từ chính `config/config.yaml`, đọc giống cách
`heartbeat_check.py` đọc (`yaml.safe_load`, key `real_order_account`). Đặt trong một helper nhỏ của file
test. Không đổi gì trong `scripts/heartbeat_check.py`.

→ kiểm chứng bằng: phá thử trên **bản sao tạm** của config, không sửa `config/config.yaml` thật. Nếu test
không nhận được đường dẫn config thì đặt key thành một số giả bằng monkeypatch ở tầng đọc. Mục tiêu: chứng
minh assert theo config chứ không theo chuỗi viết cứng. Ghi rõ đã phá thử thế nào.

## Giới hạn

- **KHÔNG commit, KHÔNG push.** Không build/restart container, không gửi Telegram, không chạy gì có
  `--send`. Không chạy `record_vn30f_orderbook.py` thật: nó mở kết nối SSI.
- **Chỉ sửa:**
  - `scripts/check_golive_gate.py` (`main`);
  - sáu file của Việc 2 (chỉ định nghĩa hàm và import);
  - `tests/test_check_golive_gate.py`;
  - `tests/test_heartbeat_check.py` (ba assert và helper).

  Không sửa `_db_common.py`.
- **`record_vn30f_orderbook.py` và `check_orderbook_daily.py` là job theo lịch, chạy thẳng từ cây làm
  việc** (08:40 và 15:30 ngày giao dịch). Làm trong git worktree và chép vào repo chính **trước 08:00 thứ Hai
  05/10**. Sau khi chép, chạy ngay `uv run python -c "import scripts.record_vn30f_orderbook,
  scripts.check_orderbook_daily"` từ gốc repo chính. Lệnh phải thoát 0.
- **GitNexus:** chạy `npx --no-install gitnexus impact <tên> --repo AI_auto_trading_system` cho
  `resolve_dsn`/`load_dotenv` (chỉ để biết, không sửa) và cho `main` của cổng. Sau khi sửa thì chạy
  `detect_changes`; nếu nó báo 0 thay đổi, chạy `npx gitnexus analyze` rồi đo lại.
- Trước khi chạy bộ đầy đủ:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng.

## Tiêu chí hoàn thành

1. **AST theo hàm** (`HEAD` với bản mới), dán kết quả:
   - sáu file Việc 2: chỉ mất `_load_dotenv` và đổi phần import, không hàm nào khác đổi;
   - `check_golive_gate.py`: chỉ `main`.
2. **Ba phá thử** như trên. Mỗi lần ghi nguyên văn dòng đỏ, khôi phục, rồi đối chiếu hash.
3. **Hai lần chạy cổng thật** (có và không `--dsn`); dán dòng mục 7 của mỗi lần.
4. `ruff` sạch. `uv run pytest -q` ≥ **1.762 passed** cộng số test mới, 0 failed.

## Báo cáo

`docs/superpowers/research/2026-10-03-dot-152-gom-viec-nho.md`: số đo nguyên văn, brief sai ở đâu, cái gì
không kiểm được.
