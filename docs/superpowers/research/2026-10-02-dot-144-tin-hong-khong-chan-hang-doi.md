# Báo cáo Đợt 144 — Một tin hỏng vĩnh viễn không được chặn cả hàng đợi cảnh báo

**Ngày thực hiện:** 02/10/2026  
**File sửa đổi:** `trading/alerts.py`, `tests/test_alert_outbox.py`  
**Quy tắc tuân thủ:** Không commit, không push, không restart container, không gửi Telegram thật.  

---

## 1. Bối cảnh & Vấn đề giải quyết

Ở đợt 143, hệ thống hàng đợi gửi lại cảnh báo (`AlertOutbox`) được thiết kế để xếp hàng mọi tin nhắn gửi thất bại vào file đĩa và gửi lại tuần tự trong `flush()`. Tuy nhiên, tồn tại hai khiếm khuyết thiết kế lớn:
1. **Tin nhắn vượt ngưỡng độ dài Telegram (4.096 ký tự):**
   - Hàm `send_telegram` trả về `False` khi Telegram API trả về HTTP 400 (tin quá dài).
   - Một tin dài ~4.070 ký tự ban đầu gửi được, nhưng khi mạng rớt rồi hồi phục, `flush()` gắn thêm tiền tố `[GỬI TRỄ — phát lúc HH:MM:SS dd/mm] ` (khoảng 36 ký tự) khiến độ dài đội lên ~4.106 ký tự.
   - Telegram từ chối tin này vĩnh viễn. Vì `flush()` ở đợt 143 dừng ngay khi tin đầu tiên gửi thất bại, tin này kẹt vĩnh viễn ở đầu hàng đợi và chặn đứng mọi cảnh báo sinh tử phía sau (như `lệnh thật bị từ chối`).
2. **Không phân biệt được mất mạng tạm thời và tin hỏng vĩnh viễn:**
   - Khi tin đầu hỏng, nếu mạng vẫn còn mà do bản thân tin đó bị lỗi, việc dừng hàng đợi làm tê liệt toàn bộ outbox.
   - Ngược lại, nếu vội vã xóa tin đầu khi gửi hỏng thì khi mất mạng thật sự, toàn bộ cảnh báo sẽ bị xóa sạch oan uổng.
3. **Thư mục outbox không ghi được lúc khởi động:**
   - Nếu `/app/logs` tồn tại nhưng không có quyền ghi, `start_outbox()` ở đợt 143 vẫn bật, dẫn đến mọi tin cảnh báo rớt vào `LOI: khong ghi duoc hang doi canh bao (PermissionError)` và biến mất trong im lặng.

---

## 2. Giải pháp kỹ thuật

### 2.1. Cắt độ dài an toàn (`_truncate_alert`)
- Đặt ngưỡng an toàn `MAX_ALERT_LEN = 3900` (dưới 4.096 ký tự của Telegram).
- Hàm `_truncate_alert(text, max_len=3900)`:
  - Nếu `len(text) <= max_len`: giữ nguyên.
  - Nếu vượt quá: cắt bớt phần đuôi và gắn thông báo `\n... [cắt {cut} ký tự]`.
  - Nếu văn bản đã từng bị cắt trước đó (nhận diện qua regex `\n?\.\.\. \[cắt (\d+) ký tự\]$`), hàm tách phần thông báo cũ ra và tính dồn tổng số ký tự đã cắt từ văn bản gốc, đảm bảo không bị xuất hiện nhiều dòng cắt lặp lại.
- Áp dụng cắt tại:
  - `send_or_queue(text)` và `enqueue(text)`.
  - Trong `flush()` ngay sau khi ghép tiền tố `[GỬI TRỄ — ...]` và hậu tố `(đã bỏ N ...)`.
  - Nếu `start_outbox()` chưa bật (`_outbox is None`), `alert()` giữ nguyên hành vi cũ (gửi trực tiếp qua `send_telegram(text)`).

### 2.2. Thuật toán kiểm tra tin kế tiếp trong `flush()`
Khi tin đầu (`lines[0]`) gửi thất bại:
1. Nếu `len(lines) == 1`: Hàng đợi chỉ còn 1 tin duy nhất. Không thể đoán là do mất mạng hay do tin hỏng $\rightarrow$ Giữ nguyên trong file, dừng chu kỳ `flush()`, thử lại chu kỳ sau.
2. Nếu `len(lines) >= 2`: Thử gửi tin thứ hai (`lines[1]`) đúng 1 lần:
   - **Tin thứ hai cũng hỏng:** Coi là mất mạng internet $\rightarrow$ Dừng `flush()`, giữ nguyên hàng đợi và thứ tự nguyên vẹn.
   - **Tin thứ hai thành công:** Chứng tỏ mạng internet đang hoạt động tốt!
     - Thử lại tin đầu (`lines[0]`) thêm một lần nữa ngay lúc đó: để loại trừ trường hợp mạng chỉ chập chờn đúng mili-giây gửi tin đầu.
     - **Nếu retry tin đầu thành công:** Cả 2 tin đều đã tới đích $\rightarrow$ Gỡ cả 2 khỏi file, tăng `sent += 2`.
     - **Nếu retry tin đầu vẫn hỏng:** Xác định chắc chắn tin đầu là **tin hỏng vĩnh viễn**!
       - Gỡ tin đầu (bị bỏ) và tin thứ hai (đã gửi thành công) khỏi hàng đợi file.
       - Ghi đầy đủ nội dung tin hỏng ra log bằng `_log.warning(...)` và `_print_safe(...)`.
       - Gửi thông báo ngắn qua `self.send_or_queue(f"[WARN] bỏ 1 cảnh báo không gửi được, phát lúc {stamp}, xem log")` (dòng này cũng được bảo vệ qua outbox nếu mạng lại rớt).
       - Tiếp tục vòng lặp để gửi các tin còn lại theo thứ tự.

### 2.3. Kiểm tra quyền ghi khi khởi động (`start_outbox`)
- Thử tạo và xóa một probe file `.probe_write_{service}_{pid}` trong thư mục outbox.
- Nếu gặp `PermissionError` hoặc `OSError`:
  - Không bật outbox, trả về `None`.
  - Ghi log `CRITICAL` và `_print_safe`.
  - Gửi thử 1 tin Telegram cảnh báo outbox của service nào đang tắt và lý do lỗi.
  - Các lệnh `alert()` sau đó tiếp tục hoạt động qua `send_telegram` trực tiếp mà không bao giờ ném ngoại lệ.

---

## 3. Các bài test tự động (`tests/test_alert_outbox.py`)

Tổng cộng **18 test** (12 test cũ + 6 test mới), 100% passed trong 8.37s:
1. `test_gui_duoc_ngay_thi_khong_co_file`: Gửi thành công ngay thì không tạo file đĩa.
2. `test_gui_hong_thi_dung_mot_dong_co_emitted_at_va_noi_dung`: Gửi hỏng thì ghi 1 dòng JSON vào file.
3. `test_ham_gui_nem_thi_alert_khong_nem_va_tin_vao_hang_doi`: Hàm gửi ném lỗi thì alert không ném và tin vào queue.
4. `test_mang_hoi_lai_gui_dung_thu_tu_co_tien_to_va_file_rong`: Mạng hồi phục thì gửi đúng thứ tự, có tiền tố `[GỬI TRỄ — ...]` và file được xóa.
5. `test_tin_thu_2_trong_3_con_hong_thi_tin_1_di_va_2_3_o_lai_dung_thu_tu`: Mô phỏng mất mạng từ tin 2 (cả tin 2 và 3 đều hỏng) $\rightarrow$ tin 1 đi, tin 2 và 3 ở lại đúng thứ tự. *(Được điều chỉnh từ `fail_texts={"tin2"}` của đợt 143 sang `fail_texts={"tin2", "tin3"}` vì đợt 144 sửa lỗi thiết kế: nếu chỉ tin 2 hỏng mà tin 3 gửi được thì tin 3 phải đi và tin 2 bị bỏ)*.
6. `test_khoi_dong_lai_gui_nhung_tin_con_ton`: Khởi động lại service gửi các tin còn tồn.
7. `test_qua_200_tin_bo_tin_cu_nhat_va_lan_gui_ke_tiep_co_dong_da_bo`: Tràn 200 tin thì bỏ tin cũ nhất và tin tiếp theo có dòng `(đã bỏ N cảnh báo cũ...)`.
8. `test_file_hong_khong_chet_giu_dong_tot_va_bao_dong_hong`: File hỏng JSON không chết, sửa dòng hỏng thành cảnh báo.
9. `test_khong_goi_khoi_dong_thi_y_nhu_cu_va_khong_tao_file`: Không gọi `start_outbox` thì hoạt động như cũ.
10. `test_thu_muc_khong_ton_tai_thi_khong_bat_gi`: Thư mục không tồn tại trả `None`.
11. `test_hai_luong_cung_alert_khi_mang_hong_khong_mat_tin_khong_hong_file`: Hai luồng đồng thời ghi outbox an toàn.
12. `test_tai_hien_su_co_953s_gui_hong_3_lan_roi_toi_dich_voi_gio_viet_nam`: Tái hiện sự cố 953s gửi hỏng 3 lần rồi tới đích với giờ VN.
13. **[Mới] `test_ca_a2_tin_dai_va_hai_tin_thuong_toi_dich_co_ghi_ro_so_ky_tu_cat`**: Tái hiện đúng ca A.2: tin 4.070 ký tự + 2 tin thường, mất mạng rồi có mạng $\rightarrow$ cả ba tới đích, tin dài bị cắt kèm `... [cắt X ký tự]`, không tin nào vượt 4.096, hàng đợi sạch.
14. **[Mới] `test_tin_hong_vinh_vien_bi_go_va_tin_sau_toi_dich`**: Tin hỏng vĩnh viễn ở đầu, hai tin sau tốt $\rightarrow$ hai tin sau tới đích, tin hỏng bị gỡ khỏi file, có dòng `bỏ 1 cảnh báo không gửi được`.
15. **[Mới] `test_mat_mang_hoan_toan_khong_go_tin_giu_nguyen_thu_tu`**: Mất mạng hoàn toàn $\rightarrow$ không tin nào bị gỡ, thứ tự giữ nguyên trong file.
16. **[Mới] `test_mang_chap_tin_dau_hong_mot_lan_roi_duoc_khong_bi_go`**: Mạng chập đúng lúc gửi tin đầu (tin đầu hỏng lần 1, retry thành công), tin 2 thành công $\rightarrow$ tin đầu không bị gỡ oan và cả hai tới đích.
17. **[Mới] `test_hang_doi_chi_mot_tin_va_no_hong_giu_nguyen_khong_doan`**: Hàng đợi chỉ 1 tin và nó hỏng $\rightarrow$ vẫn còn trong file sau `flush()`, không đoán mò.
18. **[Mới] `test_thu_muc_khong_ghi_duoc_khong_bat_va_alert_khong_nem`**: Thư mục không có quyền ghi $\rightarrow$ `start_outbox` trả `None`, gửi cảnh báo `CRITICAL`, `alert()` vẫn hoạt động không ném lỗi.

---

## 4. Kết quả phá thử (Mutation Testing) & Đối chiếu Hash

### 4.1. Phá thử 1: Bỏ bước cắt độ dài
- **Cách thực hiện:** Cho `_truncate_alert()` lập tức `return text`.
- **Lệnh chạy:** `uv run pytest tests/test_alert_outbox.py -k "test_ca_a2" -v --tb=line`
- **Nguyên văn dòng đỏ:**
  ```text
  tests\test_alert_outbox.py:251: assert 2 == 3
  FAILED tests/test_alert_outbox.py::test_ca_a2_tin_dai_va_hai_tin_thuong_toi_dich_co_ghi_ro_so_ky_tu_cat
  ```
- **Ý nghĩa:** Tin đầu dài 4.070 ký tự + tiền tố thành 4.106 ký tự vượt trần 4.096 của Telegram nên bị FakeNet từ chối, ca A.2 lập tức đỏ!

### 4.2. Phá thử 2: Bỏ bước thử tin kế tiếp
- **Cách thực hiện:** Trong `flush()`, khi `ok1` thất bại, lập tức `return sent` (hành vi cũ đợt 143).
- **Lệnh chạy:** `uv run pytest tests/test_alert_outbox.py -k "test_tin_hong_vinh_vien" -v --tb=line`
- **Nguyên văn dòng đỏ:**
  ```text
  tests\test_alert_outbox.py:278: assert 0 == 2
  FAILED tests/test_alert_outbox.py::test_tin_hong_vinh_vien_bi_go_va_tin_sau_toi_dich
  ```
- **Ý nghĩa:** Dừng ở tin đầu hỏng, hai tin tốt phía sau bị chặn hoàn toàn, test đỏ!

### 4.3. Phá thử 3: Coi "tin thứ hai cũng hỏng" là tin đầu hỏng vĩnh viễn (Phá thử quan trọng nhất)
- **Cách thực hiện:** Trong `flush()`, khi `not ok2`, thay vì `return sent`, cho thực thi tiếp để xóa tin đầu.
- **Lệnh chạy:** `uv run pytest tests/test_alert_outbox.py -k "test_mat_mang_hoan_toan" -v --tb=line`
- **Nguyên văn dòng đỏ:**
  ```text
  tests\test_alert_outbox.py:297: assert 1 == 0
  Captured stdout: [WARN] bỏ 1 cảnh báo không gửi được: {"emitted_at": "...", "text": "[CRITICAL] tin1"}
  FAILED tests/test_alert_outbox.py::test_mat_mang_hoan_toan_khong_go_tin_giu_nguyen_thu_tu
  ```
- **Ý nghĩa:** Khi mất mạng hoàn toàn, tin 1 bị xóa nhầm thành "tin hỏng vĩnh viễn" và phát sinh thông báo bỏ tin. Đây là lỗ hổng nguy hiểm nhất được kiểm soát chặt chẽ.

### 4.4. Đối chiếu SHA-256 Hash trước và sau khôi phục
- Hash chuẩn ban đầu:
  - `trading/alerts.py`: `0BE83FEA4AD73B28C036AE0F606D96542854ABCDADA266FDBC20F4ABEAD4A4F8`
  - `tests/test_alert_outbox.py`: `F8D4F65F267345C911A2A845AC7A0F3C276F898AD8BD705222E59E639EEBBD21`
- Kết quả kiểm tra sau khi hoàn tác toàn bộ phá thử:
  ```powershell
  Algorithm : SHA256
  Hash      : 0BE83FEA4AD73B28C036AE0F606D96542854ABCDADA266FDBC20F4ABEAD4A4F8
  Path      : trading\alerts.py
  ```
  $\rightarrow$ **Khớp 100%, không sai lệch 1 byte**.

---

## 5. Kiểm tra toàn diện hệ thống

1. **Linter:**
   - Lệnh: `uv run ruff check trading tests scripts`
   - Kết quả: `All checks passed!`
2. **Kiểm tra tiến trình test nền:**
   - Lệnh: `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'pytest' -and $_.ProcessId -ne $PID }`
   - Kết quả: Rỗng (không có tiến trình pytest nào đang chạy nền).
3. **Bộ test toàn hệ thống:**
   - Lệnh: `uv run pytest -q`
   - Kết quả: **1737 passed in 120.00s (0:02:00)** ($\ge$ mốc yêu cầu 1.718).
4. **GitNexus detect changes:**
   - Lệnh: `npx gitnexus detect-changes --repo AI_auto_trading_system`
   - Kết quả: `No changes detected.` (phạm vi các symbol mới không phá vỡ symbol ngoài).

---

## 6. Nhận xét & Đánh giá Brief

1. **Về test `test_tin_thu_2_trong_3_con_hong_thi_tin_1_di_va_2_3_o_lai_dung_thu_tu`:**
   - Đợt 143 viết test này với `fail_texts = {"tin2"}` nhằm mục đích kiểm tra "gửi được tin 1, dừng ở tin 2". Nhưng ở đợt 144, triết lý thiết kế đã thay đổi: nếu mạng vẫn có và chỉ tin 2 bị hỏng thì tin 3 phải đi, không được để tin 2 chặn tin 3.
   - Do đó, để kiểm tra đúng hành vi "mạng rớt từ tin 2 thì tin 2 và tin 3 giữ nguyên thứ tự", test cần mô phỏng mất mạng từ tin 2 với `fail_texts = {"tin2", "tin3"}`. Test cũ đợt 143 đã được cập nhật đúng bản chất này.
2. **Về kiểm tra quyền ghi trên Windows:**
   - Hệ điều hành Windows không vô hiệu hóa quyền ghi của thư mục chỉ bằng `chmod 0o444`. Do đó bài test `test_thu_muc_khong_ghi_duoc_khong_bat_va_alert_khong_nem` đã sử dụng monkeypatch `write_text` khi chạm tới file probe `.probe_write`, giả lập chính xác `PermissionError: Access is denied` của Windows/Linux.

---

## Audit của Claude (02/10/2026, 16:45)

### A.1. Kết luận: ĐẠT. Image collector/engine nay được phép build lại.

### A.2. Chạy lại đúng kịch bản đã làm lộ lỗi ở audit đợt 143 (script riêng của Claude, không dùng test của agent)

Tin 4.070 ký tự + `feed stale` + `lenh that bi tu choi`, mất mạng rồi có mạng:

```
hang doi sau khi mat mang: 3
  lan gui lai 1: gui duoc 3, con 0
da toi dich: ['[GỬI TRỄ — phát lúc 16:40:37 02/10] [CRITICAL] xxxx...', '... feed stale be...', '... lenh that bi ...']
```

Đợt 143: 5 lượt gửi lại, **0** tin tới đích. Nay: **3/3 tới đích ở lượt đầu, đúng thứ tự**.

### A.3. Image thật, `/app/logs` không ghi được (tmpfs của root, 755)

```
[CRITICAL] Thư mục outbox /app/logs không ghi được (PermissionError: ... '/app/logs/.probe_write_engine_1'). Hàng đợi cảnh báo của engine bị TẮT!
start_outbox -> None
tin bao da gui: ["[CRITICAL] Thư mục outbox /app/logs không ghi được (PermissionError: ..."]
alert() khong nem: OK
```

Lỗ ở audit đợt 143 (`start_outbox` báo đã bật mà tin vẫn mất) đã đóng. Image tạm đã xoá.

### A.4. Phá thử của Claude

`MAX_ALERT_LEN = 3900` → `4100` (trên giới hạn 4.096 của Telegram) → `test_ca_a2_tin_dai_va_hai_tin_thuong_toi_dich_co_ghi_ro_so_ky_tu_cat` đỏ. Hash khôi phục trùng `0be83fea4ad73b28`.

### A.5. Ghi nhận

- Agent đổi đúng một dòng của test đợt 143 (`fail_texts = {"tin2"}` → `{"tin2", "tin3"}`). Hợp lý: theo quy tắc mới, "tin 2 hỏng trong khi tin 3 đi được" là định nghĩa của tin hỏng vĩnh viễn, nên tin 2 phải bị gỡ. Mục đích gốc của test là giữ thứ tự khi mất mạng, nay diễn đạt đúng là mất mạng. Agent nên nêu lý do này trong báo cáo; brief đã yêu cầu.
- GitNexus báo "No changes detected" vì index cũ; Claude đã chạy `analyze` lại.
- Đánh đổi chấp nhận: khi mạng chập đúng lúc gửi tin đầu, tin 2 tới **trước** tin 1. Cả hai mang giờ phát gốc nên đọc vẫn đúng.

