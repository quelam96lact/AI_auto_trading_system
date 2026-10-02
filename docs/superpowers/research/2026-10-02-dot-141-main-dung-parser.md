# Báo cáo đợt 141 — `main` phải THỰC SỰ dùng parser, và bộ test phải bắt được khi nó không dùng

Không commit, không push, không tạo/sửa scheduled task, không restart container, không sửa `.env`. Chỉ chạy hai lệnh thật, cả hai chắc chắn chết ở bước phân tích tham số (cờ lạ). **GitNexus:** `impact` trước khi sửa trên cả 7 hàm `main` — đều **LOW**, 0 process. `detect_changes` **sau** khi sửa báo risk **HIGH** (xem mục 6 — phải cảnh báo).

## 1. Bảng rà soát (Việc 1) — trước / sau, mỗi script một dòng

`main` của mọi script mà `sched.sh` gọi (14 script, danh sách lấy từ `sched.sh` bằng `extract_python_modules`). Phân tích AST, không import.

| Script | Câu đầu tiên của `main` TRƯỚC | SAU | Khối `__main__` |
|---|---|---|---|
| `heartbeat_check` | **`if argv is not None: build_parser().parse_args(argv)`** — nhánh bỏ qua được | `build_parser().parse_args(argv)` vô điều kiện | `raise SystemExit(main(sys.argv[1:]))` (không đổi; tương đương `main()`) |
| `deploy_drift_check` | **`if argv is not None: build_parser().parse_args(argv)`** — nhánh bỏ qua được | `build_parser().parse_args(argv)` vô điều kiện | `raise SystemExit(main(sys.argv[1:]))` (không đổi) |
| `backfill_universe` | `ap = build_parser()` rồi `args = ap.parse_args(argv)` (vô điều kiện, hai câu) | `args = build_parser().parse_args(argv)` | `main()` |
| `check_orderbook_daily` | `parser = build_parser()` rồi `args = parser.parse_args(argv)` | `args = build_parser().parse_args(argv)` | `main()` |
| `record_vn30f_orderbook` | `parser = build_parser()` rồi `args = parser.parse_args(argv)` | `args = build_parser().parse_args(argv)` | `main()` |
| `stream_health_check` | `parser = build_parser()` rồi `args = parser.parse_args(argv)` | `args = build_parser().parse_args(argv)` | `main()` |
| `daily_data_check` | `args = parse_args(argv)` (hàm bọc `parse_args` → `build_parser().parse_args`) | `args = build_parser().parse_args(argv)`; hàm bọc `parse_args` thành thừa nên **xoá** | `main()` |
| `backup_check` | đã đúng khuôn | — | `try: sys.exit(main()) except …` |
| `check_silent_engine` | đã đúng khuôn | — | `sys.exit(main())` |
| `container_health_check` | đã đúng khuôn | — | `try: sys.exit(main()) except …` |
| `disk_check` | đã đúng khuôn | — | `try: sys.exit(main()) except …` |
| `engine_consumer_check` | đã đúng khuôn | — | `main()` |
| `host_preflight` | đã đúng khuôn | — | `try: sys.exit(main()) except …` |
| `restore_drill` | đã đúng khuôn | — | `try: sys.exit(main()) except …` |

Không script nào cần đặt việc gì trước câu parse (không có danh sách trắng): `STATEMENTS_ALLOWED_BEFORE_PARSE` trong test để rỗng.

**Chỉ hai script có lỗi thật** (nhánh bỏ qua được): `heartbeat_check` và `deploy_drift_check`. Năm script còn lại (4 hai-câu + `daily_data_check`) **không** có lỗi — parse vẫn vô điều kiện — nhưng không có dạng "một câu" mà brief Việc 2 đòi cho mọi script, nên tôi đã đưa về cùng khuôn (thay đổi ngữ nghĩa bằng không).

## 2. Việc 2 — sửa

- `heartbeat_check.py`, `deploy_drift_check.py`: bỏ `if argv is not None:` (và thêm chú thích 2 dòng trỏ về brief 141 và test AST); câu parse là câu đầu của `main`. Khối `__main__` giữ nguyên.
- `backfill_universe`, `check_orderbook_daily`, `record_vn30f_orderbook`, `stream_health_check`, `daily_data_check`: đúng một dòng `args = build_parser().parse_args(argv)` thay cho hai câu / hàm bọc. `daily_data_check.parse_args` bị xoá vì không còn ai gọi (đã grep).
- Không đổi logic nào khác của `main` ở bất kỳ script nào.

## 3. Việc 3 — test ghim bằng AST (`tests/test_sched_args.py`, +29 test)

- `test_main_goi_build_parser_parse_args_vo_dieu_kien_o_cau_dau[<script>]` (×14): phân tích **AST** (không import, không chạy): `main` có đúng tham số `argv`; câu lệnh đầu tiên (bỏ docstring) là `args = build_parser().parse_args(argv)` hoặc `build_parser().parse_args(argv)` — **Assign/Expr ở cấp thân hàm**, nên `if`/`try`/`with` đều bị loại; và nó phải chuyển tiếp đúng `argv`.
- `test_khoi_main_goi_ham_main[<script>]` (×14): khối `if __name__ == "__main__":` thực sự gọi `main(...)`.
- `test_cong_cu_ast_phan_biet_dung_sai`: tự kiểm công cụ — mẫu đúng qua, và các mẫu sai (`if argv is not None`, `if argv:`, hai câu `parser = …`, parse một danh sách khác, bọc trong `try`) đều bị bắt.
- Không có test nào gọi `main(["--khong-ton-tai"])` (gỡ parser thì test đó sẽ chạy job thật).

RED trước khi sửa (7 script đỏ: 2 lỗi thật + 5 chưa đúng khuôn): `FAILED …[scripts.heartbeat_check]`, `…[scripts.deploy_drift_check]`, `…[scripts.backfill_universe]`, `…[scripts.check_orderbook_daily]`, `…[scripts.daily_data_check]`, `…[scripts.record_vn30f_orderbook]`, `…[scripts.stream_health_check]`.

## 4. Phá thử (nguyên văn) và đối chiếu mã băm

SHA-256 trước: `heartbeat_check.py` `57ffd776a2e4426cb45cb1d003d7053c6fbef25702c1b869dc7d8f88f0c9f2b7`, `deploy_drift_check.py` `080c977c60ae7f81c36bc5b266e12efe7d825519064713d8db7792ccf59f273e`, `disk_check.py` `67bf805efb4745d25df15e2452fa01240474c5a5f848ae5d49825f65379429fb`.

1. **Hai phá thử trong bảng của brief — làm lại.** Phá thử 1 nguyên văn (`raise SystemExit(main())` thay `main(sys.argv[1:])`) **sau khi sửa không còn là một regression**: vì `main` giờ parse vô điều kiện nên `main()` và `main(sys.argv[1:])` cho cùng kết quả — một test không thể (và không nên) đỏ vì nó (xem mục 7). Tôi làm phá thử **tương đương** với thứ thật sự gây lỗi: khôi phục `if argv is not None:` và gọi `main()` trần:
   `FAILED tests/test_sched_args.py::test_main_goi_build_parser_parse_args_vo_dieu_kien_o_cau_dau[scripts.heartbeat_check]` — `AssertionError: scripts.heartbeat_check.main: cau lenh dau tien co hieu luc phai la `args = build_parser().parse_args(argv)` vo dieu kien, nhung la: 'if argv is not None:'` (1 failed, 45 passed).
2. **Bỏ câu parse ở `deploy_drift_check`** (phá thử 2 của brief):
   `FAILED tests/test_sched_args.py::test_main_goi_build_parser_parse_args_vo_dieu_kien_o_cau_dau[scripts.deploy_drift_check]` — `… nhung la: 'try:'` (1 failed, 45 passed).
3. **Phá thử thứ ba — bọc trong `if argv:`** (ở `disk_check`):
   `FAILED tests/test_sched_args.py::test_main_goi_build_parser_parse_args_vo_dieu_kien_o_cau_dau[scripts.disk_check]` — `… nhung la: 'if argv:'` (1 failed, 45 passed).
Sau khôi phục: `sha256sum -c` → `scripts/heartbeat_check.py: OK`, `scripts/deploy_drift_check.py: OK`, `scripts/disk_check.py: OK`; 46 passed.

## 5. Chạy thật, an toàn

```
scripts/sched.sh heartbeat --khong-ton-tai     -> EXIT=2
scripts/sched.sh deploy-drift --khong-ton-tai  -> EXIT=2
```
`logs/heartbeat.log`:
```
2026-10-02 10:51:17 heartbeat-check start
usage: heartbeat_check.py [-h]
heartbeat_check.py: error: unrecognized arguments: --khong-ton-tai
EXIT=2
```
`logs/deploy-drift.log`:
```
2026-10-02 10:51:20 deploy-drift start
usage: deploy_drift_check.py [-h]
deploy_drift_check.py: error: unrecognized arguments: --khong-ton-tai
EXIT=2
```
Có `unrecognized arguments`, không có dòng nào cho thấy job đã chạy (không có kết quả kiểm DB hay lệch triển khai).

### Lần chạy lịch thật của `heartbeat` sau khi sửa

Lịch của task `trading-heartbeat-check` gọi mỗi 5 phút trong giờ giao dịch (thứ Sáu 02/10/2026). `scripts/heartbeat_check.py` sửa lần cuối lúc **10:49:51** (khôi phục sau phá thử), nên hai lần chạy lịch dưới đây dùng đúng bản đã sửa:

```
2026-10-02 10:50:16 heartbeat-check start
EXIT=0
...
2026-10-02 10:55:03 heartbeat-check start
EXIT=0
```
(Giữa hai dòng là lần chạy cờ lạ chủ ý 10:51:17 `EXIT=2` ở trên; lần chạy lịch ngay sau nó, 10:55:03, vẫn `EXIT=0`: cờ lạ chặn được mà đường lịch thật không bị vỡ.)

## 6. Cảnh báo `detect_changes` — risk HIGH (CLAUDE.md bắt buộc cảnh báo)

`gitnexus detect_changes` (scope `all`): **risk `high`**, 28 symbol đổi, 8 process bị ảnh hưởng (`main → _get_pool`, `main → _print_safe`, `main → Is_trading_day`, `backfill_one → …` ×5). Đó **không** phải thay đổi hành vi lớn: mỗi cái là luồng `main` của chính một script, và các hàm khác (`backfill_one`, `load_symbols`, `check_orderbook_daily`, `stale_services`, …) bị liệt kê "touched" vì **hook định dạng (formatter) đã xuống dòng lại** các file đó (vd `heartbeat_check.py` 50 dòng, `check_orderbook_daily.py` 37, `backfill_universe.py` 23, `daily_data_check.py` 18 dù bỏ khoảng trắng). Thay đổi ngữ nghĩa thật nằm ở **câu đầu của `main`** ở 7 script. Nên audit bằng `git diff -w` và đọc theo `main`; phần còn lại là cosmetic.

## 7. Brief sai / tự mâu thuẫn — và cách tôi xử lý

1. **Phá thử 1 nguyên văn không còn đỏ được sau khi sửa.** `raise SystemExit(main())` ≡ `main(sys.argv[1:])` khi `main` parse vô điều kiện (`argv=None` ⇒ argparse đọc `sys.argv`). Thứ thật sự nguy hiểm là cái `if argv is not None:` đi kèm, và đó là chỗ tôi ghim (phá thử 1 tương đương ở mục 4). Đã thêm `test_khoi_main_goi_ham_main` để khối `__main__` không thể bị thay bằng thoát sớm.
2. **Phạm vi file tự mâu thuẫn.** "Chỉ sửa" hai script + `test_sched_args.py`, nhưng Việc 2 đòi "mọi script cùng một khuôn". *Ruling:* theo Việc 2 — sửa thêm 5 script (4 hai-câu + `daily_data_check`), mỗi cái đúng một dòng, ngữ nghĩa không đổi, nêu rõ ở bảng mục 1. Nếu muốn giữ phạm vi hẹp: test chỉ cần cho phép dạng hai-câu (dạng đó vẫn parse vô điều kiện), nhưng sẽ không đúng "một khuôn".
3. **Không thể "không đổi logic nào khác" mà không sửa test khác.** `main()` gọi trần dưới pytest giờ đọc `sys.argv` của pytest (`-q`, đường dẫn test…) và `argparse` chết `unrecognized arguments`. Bốn lời gọi trong test phải đổi sang `main([])`: ba ở `tests/test_heartbeat_check.py` (`rc = hc.main()` → `hc.main([])`) và một ở `tests/test_deploy_drift_check.py` (`deploy_drift_check.main()` → `main([])`). Hai file đó **không** nằm trong danh sách được sửa của brief; tôi sửa vì không còn cách nào khác và nêu ở đây. Sản xuất không đổi (cron gọi script, `argv` thật).
4. **`detect_changes` ra `high`** do nhiễu định dạng (mục 6), không do ngữ nghĩa.

## 8. Kiểm chung

`uv run pytest -q` → **1706 passed** (mốc 1677 + 29); `ruff check trading tests scripts` sạch. Hai file làm sửa bị đổi sang CRLF (`backfill_universe.py`, `deploy_drift_check.py`) đã đưa lại về LF khớp index.

## 9. Không kiểm được

- Chỉ ghim được `main` **gọi** parser; không ghim được việc **cờ hợp lệ** được script **dùng đúng** (ví dụ `--date`, `--dry-run`): đó là test riêng từng script (đợt 140 đã có cho `daily_data_check`).
- Ngoài hai lệnh chết-ở-parse ở mục 5, tôi **không** chạy lệnh nào khác của job thật, vì brief cấm chế độ gửi thật.

---

## Audit của Claude (02/10/2026, 11:15)

### A.1. Kết luận: ĐẠT, nhận toàn bộ.

### A.2. Diff ồn vì hook định dạng — Claude so cây cú pháp thay vì so dòng

Claude so AST của từng file `.py` ở `HEAD` với cây làm việc, theo từng hàm (bỏ qua định dạng hoàn toàn):

```
scripts/backfill_universe.py      khac AST: ['main']
scripts/check_orderbook_daily.py  khac AST: ['main']
scripts/daily_data_check.py       khac AST: ['main', 'parse_args']   (ham boc bi xoa, khong con ai goi)
scripts/deploy_drift_check.py     khac AST: ['main']
scripts/heartbeat_check.py        khac AST: ['main']
scripts/record_vn30f_orderbook.py khac AST: ['main']
scripts/stream_health_check.py    khac AST: ['main']
```

Ba câu đầu của mỗi `main`, cũ và mới: chỉ câu parse đổi; không câu nào bị đổi thứ tự. Số câu giảm đúng 1 ở các script gộp `parser = build_parser()` / `args = parser.parse_args(argv)` thành một câu.

GitNexus chấm **HIGH, 8 luồng**, và liệt kê cả `backfill_one`. AST cho thấy `backfill_one` **không đổi nghĩa**: hook chỉ xuống dòng lại một biểu thức `if/else` và một điều kiện `or`. GitNexus đo theo dòng diff nên tính cả phần định dạng. Không file nào trong `trading/` bị chạm.

### A.3. Phá thử của Claude — khác ba phá thử của agent

| Phá thử | Kết quả |
|---|---|
| `stream_health_check`: `args, _ = build_parser().parse_known_args(argv)` | 2 test đỏ, gồm `test_main_goi_build_parser_parse_args_vo_dieu_kien_o_cau_dau[scripts.stream_health_check]` |
| `heartbeat_check`: khối `__main__` thành `raise SystemExit(0)` | `test_khoi_main_goi_ham_main[scripts.heartbeat_check]` đỏ |
| `record_vn30f_orderbook`: chèn một câu có tác dụng **trước** câu parse | `test_main_goi_..._o_cau_dau[scripts.record_vn30f_orderbook]` đỏ |

Hash khôi phục trùng ở cả ba. Hai phá thử Claude dùng ở audit đợt 140 (khi đó 17/17 xanh) nay đều đỏ, theo báo cáo của agent.

### A.4. Chạy thật

Lịch thật của `heartbeat` sau khi sửa: 11:00:03, 11:05:04, 11:10:11 — cả ba `EXIT=0`. `ruff` sạch; **1.706 passed**.

### A.5. Các điểm agent nêu — chấp nhận

- **Phạm vi:** brief tự mâu thuẫn ("chỉ sửa hai script" và "mọi script cùng một khuôn"). Agent theo bước 2 và nói rõ. Lỗi brief.
- **4 test ngoài danh sách:** `main()` gọi trần dưới pytest giờ đọc `sys.argv` của pytest, nên phải truyền `main([])`. Hệ quả tất yếu của việc parse vô điều kiện; cron không bị ảnh hưởng.
- **Phá thử 1 của brief không còn ý nghĩa:** đúng. Khi `main` parse vô điều kiện thì `main()` và `main(sys.argv[1:])` cho cùng kết quả. Agent thay bằng một phá thử tương đương.

