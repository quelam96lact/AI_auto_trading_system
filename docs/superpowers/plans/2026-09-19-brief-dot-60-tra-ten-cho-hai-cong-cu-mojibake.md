# Brief đợt 60 — Trả tên cho hai công cụ mojibake

Ngày giao: 19/09/2026 (thứ Bảy, tối).
Base: `7cd12ab` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

Việc nhỏ, không mơ hồ — rút gọn quy trình theo đúng đánh đổi ở CLAUDE.md, nhưng vẫn giữ phạm vi
phẫu thuật và tiêu chí kiểm chứng rõ ràng.

---

## 0. Bối cảnh

Đợt 58 phát hiện `scripts/.fix_mojibake.py` và `scripts/.scan_mojibake.py` đang được git theo
dõi **trái luật riêng của repo** — `.gitignore` loại mọi file bắt đầu bằng dấu chấm, nhưng hai
file này lọt vào vì `git add` tường minh hôm 18/09.

Đợt 59 đã giải đúng bài toán này cho `scripts/.probe_dead_man_switch.py`: thay vì mở thêm ngoại
lệ trong `.gitignore`, **bỏ dấu chấm** — biến nó thành công cụ chính thức. `scripts/README.md`
mục 2.1 giờ nói rõ: *"Mọi công cụ chẩn đoán hoặc vận hành cần thiết trên môi trường VPS PHẢI là
script chính thức không mang dấu chấm đầu tên"*.

Hai file mojibake là **công cụ bảo trì thật**, không phải vết nghiên cứu đã đóng (khác hẳn 14
file `.spike_*`/`.repro_*` mà đợt 58 xếp loại "đã hết dùng"). Lỗi mojibake **đã xảy ra thật**
ngày 18/09 và công cụ này đã sửa được nó. Áp đúng tiền lệ vừa lập với
`probe_dead_man_switch.py`: **đổi tên, không mở ngoại lệ**.

Đã kiểm trước khi giao: `grep` toàn bộ `scripts/`, `tests/`, `*.md` — **không có script hay test
nào gọi hai file này bằng tên**, chỉ có nhắc tới trong các báo cáo lịch sử ở `docs/superpowers/research/`
(không sửa).

---

## 1. Phạm vi

| File | Việc |
|---|---|
| `scripts/.fix_mojibake.py` → `scripts/fix_mojibake.py` | đổi tên |
| `scripts/.scan_mojibake.py` → `scripts/scan_mojibake.py` | đổi tên |
| `scripts/README.md` | sửa dòng 14 (bảng), không đụng gì khác |
| `docs/superpowers/research/2026-09-19-dot-60-*.md` | **mới** | báo cáo |

**Không đụng file nào khác.** Đặc biệt: **không sửa** `docs/superpowers/research/*.md` cũ (chúng
là biên bản lịch sử, việc tên file cũ nhắc tới trong đó không cần cập nhật).

Ràng buộc chung: không xoá nội dung file, chỉ đổi tên; **không commit, không push**; mọi
`git diff`/`git status` copy từ lệnh.

---

## Task 1 — Đổi tên, giữ nguyên nội dung

1. `git mv scripts/.fix_mojibake.py scripts/fix_mojibake.py`
2. `git mv scripts/.scan_mojibake.py scripts/scan_mojibake.py`

   Nếu `git mv` báo lỗi vì file cũ không được theo dõi đúng cách, dùng `Move-Item` (PowerShell)
   rồi `git add scripts/fix_mojibake.py scripts/scan_mojibake.py` — nói rõ bạn đã làm cách nào
   trong báo cáo.

3. **Không sửa nội dung bên trong hai file.** Nếu chúng tự tham chiếu tên chính mình (ví dụ
   trong docstring hoặc thông báo lỗi), sửa đúng chỗ đó — và chỉ đúng chỗ đó.

---

## Task 2 — Cập nhật `scripts/README.md`

Dòng 14 hiện tại:

```
| **`.fix_*` / `.scan_*` | Công cụ bảo trì codebase | Tiện ích một lần / định kỳ | Quét và sửa lỗi hệ thống/dữ liệu (ví dụ: phát hiện và sửa mojibake encoding). |
```

Hai công cụ này giờ **không còn mang dấu chấm**, nên chúng thuộc hàng "Không dấu chấm" ở dòng 15,
không thuộc bảng tiền tố dấu chấm nữa. Sửa:

1. **Xoá dòng 14** khỏi bảng (không còn ví dụ nào cho tiền tố `.fix_*`/`.scan_*` sau khi đổi tên).
2. **Thêm vào câu LƯU Ý ở dòng 15** — nối tiếp danh sách công cụ không dấu chấm đã có
   (`spike_ssi_sdk_auth.py`, v.v.) — một câu ngắn nêu `fix_mojibake.py` và `scan_mojibake.py` là
   công cụ bảo trì chính thức, dùng khi phát hiện lỗi mã ký tự (xem
   `docs/superpowers/research/2026-09-18-dot-52-*.md` phần liên quan mojibake để trích dẫn đúng
   ngữ cảnh — **đọc trước khi viết câu**, đừng đoán).

**Không sửa gì khác trong file.** Đặc biệt không đụng dòng 23 (nó đã lấy đúng
`probe_dead_man_switch.py` làm ví dụ, không liên quan tới hai file này).

---

## 2. Kiểm chứng

1. `Test-Path scripts/.fix_mojibake.py` và `scripts/.scan_mojibake.py` → **cả hai `False`**.
2. `Test-Path scripts/fix_mojibake.py` và `scripts/scan_mojibake.py` → **cả hai `True`**.
3. `git status --short` cho thấy đây là **rename** (`R`) nếu `git mv` dùng được, hoặc
   `D` + `A` nếu phải làm thủ công — nêu rõ cái nào xảy ra.
4. Chạy thử cả hai công cụ để chứng minh chúng vẫn hoạt động sau khi đổi tên:
   ```
   uv run python scripts/scan_mojibake.py docs/superpowers/research
   ```
   Dán nguyên văn output — kỳ vọng vẫn là `"KHONG tim thay dau vet mojibake nao"` như trước khi
   đổi tên (đây là phép chứng minh đổi tên không làm hỏng gì, không phải để tìm lỗi mới).
5. `grep` lại toàn bộ `scripts/`, `tests/`, `trading/` với tên cũ (`\.fix_mojibake` và
   `\.scan_mojibake`) → phải **rỗng**.
6. `uv run pytest -q` (mốc **807**) và `uv run ruff check trading tests scripts` — cả hai không
   liên quan trực tiếp tới đợt này nhưng phải vẫn xanh, chứng minh đổi tên không phá gì.

---

## 3. Báo cáo cho Claude

1. `git status --short` (trước và sau khi `git add`).
2. `git diff scripts/README.md`.
3. Output của `scripts/scan_mojibake.py` chạy sau khi đổi tên.
4. Kết quả `grep` tên cũ — phải rỗng.
5. Ba dòng: test pass, ruff, xác nhận `Test-Path` bốn lệnh ở mục Kiểm chứng.

**Không commit, không push.**
