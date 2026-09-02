# Brief — Agent B (người đã làm đợt 8: cổng Docker)

Giao tối 02/09/2026. Hai phần, **phần 2 bị khoá thời gian**.

Bạn được giao tiếp phần này vì bạn đã ở sâu trong chuỗi chuông báo —
`run_if_docker_up.sh`, `_print_safe`, khuôn "in trước, gửi sau".

**Trước hết: báo cáo đợt 8 của bạn đã được audit và CHẤP NHẬN**, commit
`0c9c85b`. Claude kiểm bổ sung phần bạn không quan sát được (lúc bạn kiểm là
17:15, ngoài khung giờ): 6 tình huống trên `config.yaml` thật đều đúng, gồm
`03/09 09:15 → kêu`, `02/09 ngày lễ → im`, `thứ bảy → im`, và
`03/09 12:00 nghỉ trưa → kêu`.

Hai điều đáng ghi nhận cụ thể: cách bạn gọi `in_bar_check_window` tại mốc 10:00
để tách phần *ngày* khỏi phần *giờ* thay vì chép điều kiện ngày lễ — đúng tinh
thần `4ea4c8d`; và việc bạn tự phát hiện `python -m` khi gặp
`ModuleNotFoundError` lúc chạy thật, thay vì báo xong dựa trên đọc code.

**Một đính chính về brief cũ, lỗi của Claude:** brief đợt 8 nói suite "đang có
một test đỏ". Bạn báo `355 passed` và bạn **đúng** —
`tests/test_backtest_cli.py:15` có `pytestmark = pytest.mark.integration` nên
cả module bị loại khỏi `-m "not integration"`. Test đó chỉ đỏ ở suite đầy đủ.

---

## PHẦN 1 — Làm ngay: xoay log trên Windows

Việc nhỏ, và Claude nói thẳng: **đây là mục nhỏ nhất trong sổ tồn đọng.** Nếu
chủ dự án muốn bạn chờ tới 14:45 ngày 03/09 rồi làm phần 2, đó là lựa chọn
hợp lệ — đừng bịa thêm việc để lấp chỗ trống.

Lý do nó vẫn đáng làm bây giờ: `DEPLOYMENT.md §8` có logrotate cho Ubuntu
nhưng **không có gì cho Windows**, và đây là thứ phải có trước khi chuyển sang
VPS. Con số đã đổi kể từ lần đo trước: ngày Docker tắt, `heartbeat.log` nhận
thêm ~85 dòng SKIP (đo 02/09: 85 SKIP / 325 dòng).

### Ràng buộc

- Chỉ sửa `scripts/`, `tests/`, `DEPLOYMENT.md`.
- **Không chạm `trading/`, `config/config.yaml`.** Chạm `trading/` ⇒ dựng lại
  container ⇒ làm bẩn phiên 03/09.
- **Không sửa `scripts/heartbeat_check.py`** — file nhạy cảm nhất repo, đã bị
  sửa ba lần ngày 01/09 và một lần làm chuông chết câm.
- **Không commit, không push.** Claude audit rồi mới commit.
- Không in giá trị bí mật. `.env` không sửa. Không xoá log đang có.
- Ngoài phạm vi thì báo cáo, không tự sửa.

### Việc

Xoay log cho các file trong `logs/` mà đám scheduled task ghi vào
(`heartbeat.log`, `daily-data-check.log`, `backfill.log`, `deploy-drift.log`).

Yêu cầu thiết kế:

1. **Dùng chung một chỗ như `sched.sh`**, đừng viết riêng cho Windows rồi mai
   lại viết bản Ubuntu — `4ea4c8d`: một công thức hai nơi thì sớm muộn lệch.
   Nếu chỗ đúng là `run_if_docker_up.sh` (nó đã là cửa ngõ duy nhất ghi log)
   thì làm ở đó và nói rõ vì sao.
2. **Xoay theo kích thước, không theo ngày.** Ngày nghỉ không sinh log, nên
   xoay theo ngày sẽ tạo ra một đống file rỗng.
3. **Không bao giờ được làm hỏng việc ghi log**, kể cả khi xoay thất bại (đĩa
   đầy, file bị khoá bởi tiến trình khác — chuyện thường trên Windows). Ưu
   tiên: mất bản xoay còn hơn mất dòng log.
4. Giữ vài bản cũ rồi xoá dần. Số bản là quyết định của bạn — **nêu rõ con số
   và lý do**, đừng để mặc định ngầm.

→ *Kiểm chứng:* test tất định, không `sleep`, không so giờ tường (đồng hồ
Windows ~15,6 ms làm test giờ tường chập chờn — đã dính 01/09). Ít nhất:
   - file vượt ngưỡng ⇒ được xoay, nội dung cũ **không mất**;
   - file dưới ngưỡng ⇒ **không** bị đụng;
   - xoay thất bại ⇒ **vẫn ghi được dòng log mới** (đây là test quan trọng
     nhất — dán output đỏ khi phá).

**Kiểm chứng phá hoại bắt buộc** cho test thứ ba: phá cho việc ghi log chết khi
xoay hỏng, dán output đỏ nguyên văn, rồi khôi phục.

Cập nhật `DEPLOYMENT.md §8` để phần Windows không còn trống.

### Tiêu chí hoàn thành phần 1

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Cơ chế xoay | test mới xanh (`uv run pytest tests/<file> -v`) |
| 2 | Phá hoại | output đỏ nguyên văn của test "xoay hỏng vẫn ghi được log" |
| 3 | Chạy thật | dựng file log giả vượt ngưỡng, chạy cổng, cho thấy đã xoay và dòng mới vẫn vào |
| 4 | Không hồi quy cổng | `scripts/run_if_docker_up.sh audit.log audit echo hi` → log có `start`, `hi`, `EXIT=0`; xoá file tạm sau khi xong |
| 5 | Không hồi quy suite | `uv run pytest -m "not integration" -q` — không đỏ thêm |
| 6 | Lint | `uv run ruff check trading tests scripts` sạch |
| 7 | Tài liệu | `DEPLOYMENT.md §8` có phần Windows |

---

## PHẦN 2 — KHOÁ tới sau 14:45 ngày 03/09

**Không bắt đầu trước mốc đó.** Chờ Claude bật đèn.

### B2 — Gộp `_print_safe` vào `trading/alerts.py`

Nay có **ba bản**: `scripts/heartbeat_check.py:164`,
`scripts/deploy_drift_check.py`, và `scripts/docker_down_alert.py` (bản bạn
vừa thêm). Đã diff hai bản đầu: thân hàm **giống hệt**, chỉ docstring khác.
Chưa lệch hành vi — nhưng `4ea4c8d` đã dạy: một công thức ba nơi thì chắc chắn
sẽ lệch, và đây là hàm an toàn của chuông báo.

**Vì sao hoãn tới sau phiên, không phải vì sao bỏ:** gộp lại nghĩa là sửa
`heartbeat_check.py` — cái dead-man's switch đã chết câm một lần vì đúng một
dòng `print()` thêm vào (`ed17539` → `51ff6de`). Sửa chuông báo khi chưa quan
sát được nó kêu trên code mới là làm mù. Sau phiên 03/09 sẽ có tín hiệu thực
địa để xác nhận chuỗi cảnh báo còn hoạt động.

Khi mở khoá, hai điều phải giữ:

1. **Hành vi không được đổi** — `_print_safe` phải vẫn không bao giờ ném, và
   vẫn hạ cấp sang ASCII khi cp1252 không mã hoá được. Viết test cho chính
   đường hạ cấp đó trước khi gộp.
2. **Chạm `trading/alerts.py` ⇒ BẮT BUỘC dựng lại container**
   (`DEPLOYMENT.md §10`) và xác nhận bằng grep chữ ký, không chỉ bằng test.
   Đây chính là lỗi đã để collector/engine chạy image 15/08 suốt hai tuần.
