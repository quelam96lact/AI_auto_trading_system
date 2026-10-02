# Brief đợt 147 — ghim hai hành vi của `engine_consumer_check` mà bộ test đang bỏ trống

Việc rất nhỏ: **chỉ thêm test**, không sửa code chạy thật.

## Vì sao — hai phá thử của Claude khi audit đợt 146 đều sống sót

| Phá thử trên `scripts/engine_consumer_check.py` | Kết quả |
|---|---|
| `main` truyền `state_file=None` thay vì `args.state_file` (bỏ qua cờ `--state-file`, ghi vào đường dẫn thật) | **21/21 xanh** |
| `save_state` đổi `except Exception` thành `except ZeroDivisionError` (lỗi ghi file làm chết job) | **21/21 xanh** |

Code hiện tại làm đúng cả hai. Nhưng chỉ cần sửa một dòng là:
1. Cờ `--state-file` bị nuốt im lặng, và test nào gọi `main` sẽ ghi vào `logs/.engine_consumer_last_check`
   thật. Đó là họ lỗi đợt 140 (parser có nhưng không ai chứng minh `main` dùng nó) và đợt 145 (test ghi
   file thật).
2. Một lỗi ghi file (đĩa đầy, quyền) làm chết chuông 2C giữa phiên, trong khi brief đợt 146 bắt giữ
   nguyên hành vi "ghi hỏng thì in lỗi rồi chạy tiếp".

## Giới hạn

- **KHÔNG commit, KHÔNG push**, không sửa task, không restart container, không gửi Telegram thật, không
  gọi NATS thật (dùng hàm/đối tượng giả sẵn có trong `tests/test_engine_consumer_check.py`).
- **Chỉ sửa** `tests/test_engine_consumer_check.py`. Không đụng `scripts/`. Nếu thấy không thể ghim mà không
  sửa code thì **dừng và báo**, đừng sửa.
- Test **không** được ghi vào `logs/` thật. Lưới an toàn đợt 145 trong `tests/conftest.py` sẽ làm phiên
  đỏ nếu có.
- Phát hiện pytest khác đang chạy: `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng trước khi chạy bộ đầy đủ.

## Việc

1. **Test `main` truyền `--state-file` xuống:** gọi `main(["--state-file", <tmp_path>/x.json, ...])` với
   NATS và giờ giao dịch được giả lập theo cách các test sẵn có trong file đã làm. Khẳng định file
   trạng thái được ghi **đúng tại `tmp_path`**, và `run_check` nhận đúng đường dẫn đó. Chọn cách khẳng
   định nào chắc nhất và nói rõ trong báo cáo.
2. **Test lỗi ghi không làm chết job:** cho `save_json_state` (hoặc `os.replace`) ném `OSError` khi ghi.
   Khẳng định `run_check` vẫn trả **đúng mã thoát** như khi ghi thành công (0 khi khoẻ, 1 khi có cảnh
   báo), và có dòng `Không thể ghi file state` được in ra.

## Tiêu chí hoàn thành

1. Làm lại **đúng hai phá thử** ở bảng trên; mỗi cái phải làm ít nhất một test mới **đỏ**. Ghi nguyên
   văn dòng đỏ, khôi phục, đối chiếu hash `scripts/engine_consumer_check.py` (trước = sau).
2. `git diff --stat` chỉ có `tests/test_engine_consumer_check.py` (và báo cáo).
3. `ruff` sạch; `uv run pytest -q` ≥ **1.745 passed** cộng số test mới; lưới an toàn đợt 145 không đỏ.

## Báo cáo

`docs/superpowers/research/2026-10-02-dot-147-ghim-engine-consumer.md`: số đo nguyên văn, brief sai ở đâu,
cái gì không kiểm được.
