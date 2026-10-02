# Brief đợt 141 — `main` phải THỰC SỰ dùng parser, và bộ test phải bắt được khi nó không dùng

Việc nhỏ, một mục tiêu duy nhất.

## Vì sao — phá thử của Claude khi audit đợt 140

Đợt 140 cho mọi script mà `sched.sh` gọi một hàm `build_parser()`, và hành vi thật **đúng**: Claude chạy
`scripts/sched.sh deploy-drift|engine-cam|container-health --khong-ton-tai`, cả ba chết mã 2 trước khi làm
gì. Nhưng bộ test không ghim điều đó:

| Phá thử | Kết quả |
|---|---|
| `heartbeat_check.py`: `raise SystemExit(main())` thay vì `main(sys.argv[1:])` | **17/17 vẫn XANH** |
| `deploy_drift_check.py`: bỏ `if argv is not None: build_parser().parse_args(argv)` | **17/17 vẫn XANH** |

Test gọi `build_parser().parse_args(["--khong-ton-tai"])`. Nó chứng minh **parser** từ chối cờ lạ, không
chứng minh **`main` gọi parser**. Ở hai script trên, `main` chỉ parse khi `argv is not None`. Chỉ cần sửa
một dòng là cờ lại bị nuốt im lặng, tức là sáng 02/10 lặp lại (hai cảnh báo Telegram oan).

## Giới hạn

- **KHÔNG commit, KHÔNG push.** Không tạo/sửa scheduled task, không restart container, không sửa `.env`.
- **KHÔNG chạy job cảnh báo nào ở chế độ gửi thật.** Mọi lần chạy thật phải là lệnh chắc chắn chết ở
  bước phân tích tham số (cờ lạ), hoặc có `--dry-run`.
- Chỉ sửa: `scripts/heartbeat_check.py`, `scripts/deploy_drift_check.py` (chỉ `main` và khối `__main__`),
  `tests/test_sched_args.py`. Script khác chỉ được sửa nếu bước 1 dưới đây tìm ra cùng lỗi ở đó; nếu sửa
  thì nêu rõ.
- GitNexus: `impact` trước khi sửa symbol, `detect_changes` sau khi sửa.

## Việc

1. **Rà mọi script Python mà `sched.sh` gọi** (danh sách lấy từ `sched.sh`, như test đợt 140 đã làm).
   Với mỗi script, ghi vào báo cáo: `main` gọi `build_parser().parse_args(...)` **vô điều kiện** ở đầu
   hàm chưa, hay có nhánh nào bỏ qua được (như `if argv is not None`). Khối `__main__` gọi `main` thế
   nào.
2. **Sửa cho mọi script cùng một khuôn:** câu đầu tiên có hiệu lực của `main` là
   `args = build_parser().parse_args(argv)`, vô điều kiện. `argv=None` thì argparse tự đọc `sys.argv`,
   nên `main()` và `main(sys.argv[1:])` cho cùng kết quả. Không đổi logic nào khác của `main`.
3. **Test ghim, an toàn:** với mỗi script trong danh sách, phân tích **AST** của file (không import,
   không chạy) và khẳng định câu lệnh đầu tiên trong thân `main` (bỏ qua docstring) gọi
   `build_parser().parse_args(...)`, và câu đó **không** nằm trong `if`/`try`. Không test bằng cách
   gọi `main(["--khong-ton-tai"])`: nếu sau này ai đó gỡ parser, test đó sẽ chạy job thật.

   Nếu một script có lý do chính đáng phải làm việc gì trước khi parse (vd đặt mã hoá stdout), thì
   **nói rõ trong báo cáo** và cho phép đúng các câu lệnh đó đứng trước, theo một danh sách trắng
   ghi ngay trong test. Không nới lỏng chung chung.

## Tiêu chí hoàn thành

1. Bảng rà soát ở Việc 1, mỗi script một dòng: trước / sau.
2. **Làm lại đúng hai phá thử ở bảng trên** — giờ mỗi cái phải làm ít nhất một test đỏ. Thêm một phá thử
   thứ ba: bọc dòng `parse_args` trong `if argv:` ở một script bất kỳ → test đỏ. Ghi nguyên văn dòng đỏ,
   khôi phục, đối chiếu hash.
3. Chạy thật, an toàn: `scripts/sched.sh heartbeat --khong-ton-tai` và
   `scripts/sched.sh deploy-drift --khong-ton-tai` → mã ≠ 0, log có `unrecognized arguments`, không có
   dòng nào cho thấy job đã chạy.
4. Một lần chạy **lịch thật** của `heartbeat` sau khi sửa (lịch gọi mỗi 5 phút, 08:00–15:00 ngày giao
   dịch) ra `EXIT=0` trong `logs/heartbeat.log`. Dán dòng đó. Nếu bạn làm ngoài giờ đó thì ghi là
   **chưa kiểm được**; Claude sẽ kiểm ở phiên sau.
5. `ruff` sạch; `uv run pytest -q` ≥ **1.677 passed** cộng số test mới.

## Báo cáo

`docs/superpowers/research/2026-10-02-dot-141-main-dung-parser.md`. Số đo nguyên văn; brief sai ở đâu
thì nói ra; cái gì không kiểm được thì ghi là không kiểm được.
