# Quy ước và phân loại thư mục `scripts/`

Tài liệu này ghi nhận quy ước đặt tên và cách sử dụng các script trong thư mục `scripts/`. **Đọc kỹ trước khi dọn dẹp hoặc phân loại bất kỳ script nào.**

---

## 1. Bảng quy ước tiền tố

| Tiền tố | Vai trò | Tính chất | Cách sử dụng |
|---|---|---|---|
| **`.probe_*`** | Thăm dò vận hành chuyên sâu | Chỉ đọc (read-only), an toàn | Chẩn đoán nguyên nhân gốc khi hệ thống có dấu hiệu bất thường (ví dụ: sức mua tài khoản, HII câm, tick gap). Giữ lại để lặp lại phép đo đối chứng. |
| **`.spike_*`** | Thử nghiệm nghiên cứu / backtest | Throwaway, độc lập | Chạy kiểm định giả thuyết mới hoặc đo đạc chiến lược mà không can thiệp vào code production. Giữ lại làm bằng chứng cho các kết luận kỹ thuật. |
| **`.repro_*`** | Tái hiện bug (reproduction) | Cô lập, có chủ ý | Dựng lại chính xác điều kiện biên gây lỗi (ví dụ flake NATS) để phục vụ debug và viết test chặn hồi quy. |
| **Không dấu chấm** | Công cụ vận hành production / SDK | Chạy định kỳ hoặc CLI | Được `scripts/sched.sh`, test suite, hoặc tài liệu vận hành gọi trực tiếp. **LƯU Ý — đọc kỹ cơ chế, đừng chỉ đọc kết luận:** `spike_ssi_sdk_auth.py`, `spike_ssi_symbols_classify.py` và `spike_ssi_sdk_derivative_ohlc_stream.py` **không** được `import` ở bất kỳ đâu. Chúng là **bước trong runbook vận hành**: `heartbeat_check.py:308,314` và `load_token_to_db.py:2,6,31` nhắc tên chúng trong **thông báo lỗi** để bảo người vận hành phải chạy gì; `collector/backfill.py:305` nhắc tên trong một **comment**; còn `backfill_universe.py:49` đọc **file dữ liệu** `.spike_all_symbols_classified.json` chứ không gọi script sinh ra nó. Tương tự, `fix_mojibake.py` và `scan_mojibake.py` là các công cụ bảo trì chính thức (bỏ dấu chấm từ đợt 60), dùng khi phát hiện lỗi mã ký tự do xung đột cp1252/UTF-8 trên Windows. Xoá chúng thì code vẫn chạy — cái hỏng là mọi câu hướng dẫn trỏ vào hư không, và không ai dựng lại được token, bảng phân loại mã hay khắc phục encoding khi gặp sự cố. **KHÔNG XOÁ.** |

---

## 2. Cảnh báo quan trọng về "Tham chiếu"

> **"0 tham chiếu" KHÔNG có nghĩa là bỏ đi được.**
>
> 1. **Dấu chấm đầu tên mang hai ý nghĩa bắt buộc: "giữ có chủ ý cho môi trường dev, không nối vào pipeline" VÀ "không ship vào git / không đưa lên VPS production"** (được tự động loại trừ bởi `.gitignore`). Mọi công cụ chẩn đoán hoặc vận hành cần thiết trên môi trường VPS PHẢI là script chính thức không mang dấu chấm đầu tên (ví dụ `scripts/probe_dead_man_switch.py`, hoặc được mở ngoại lệ tường minh `!` trong `.gitignore`). Các công cụ mang dấu chấm được thiết kế để người vận hành chạy thủ công khi cần chẩn đoán sự cố tại máy dev, không phải để `import` trong code.
> 2. Phần lớn tham chiếu tới nhóm script này là **chuỗi thông báo hướng dẫn người vận hành** (nằm trong docstring, log hoặc thông báo lỗi) bảo người vận hành phải chạy lệnh gì. Công cụ phân tích mã tĩnh sẽ không thấy `import` nào.
> 3. Nhiều script và file dữ liệu đi kèm có quan hệ chéo: ví dụ `scripts/backfill_universe.py` đọc trực tiếp file dữ liệu `scripts/.spike_all_symbols_classified.json`, trong khi script sinh ra file đó (`spike_ssi_symbols_classify.py`) chỉ xuất hiện trong câu hướng dẫn.

---

## 3. Quy tắc khi muốn loại bỏ script

Trước khi đề xuất xoá bất kỳ file nào trong `scripts/`:
1. **Kiểm tra tham chiếu toàn diện:** Quét chuỗi tên file trong `scripts/`, `trading/`, `tests/`, `docs/` và các file cấu hình.
2. **Đọc nội dung và docstring:** Xác nhận mục đích lịch sử của file đó trước khi kết luận nó là rác.
3. **Chỉ người phụ trách/chủ dự án mới có quyền xoá.** Mọi đề xuất dọn dẹp phải lập danh sách và nêu rõ lý do trong báo cáo nghiên cứu.
