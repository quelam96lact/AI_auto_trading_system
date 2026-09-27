# Brief đợt 113 — Agent chạy diễn tập đặt/huỷ lệnh BingX trên **DEMO VST** (tiền ảo)

Ngày giao: 27/09/2026. Base: main `543a242`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push, không sửa code**. Đây là đợt **chạy và báo cáo**.

## 0. Phạm vi và giới hạn cứng

- **CHỈ `--env demo`.** Tên miền `open-api-vst.bingx.com`, tiền ảo VST. Claude kiểm ngày 27/09: key trong `.env` đọc được số dư VST là 80.002,16.
- **TUYỆT ĐỐI KHÔNG `--env live`**, dù chỉ chạy khô. Diễn tập live do chủ dự án tự chạy, vì hai lý do:
  - quy tắc đứng của dự án: agent không đặt lệnh tiền thật;
  - ví live chỉ có 8,08 USDT, dưới mức ký quỹ 2× mà script đòi.
- Chạy script diễn tập **tối đa 2 lần**:
  - lần 1 chạy khô;
  - lần 2 chạy `--send`.

  Nếu lần `--send` ra exit khác 0 thì **dừng lại, không chạy lại**, rồi báo cáo.
- Không sửa `trading/`, `scripts/`, `tests/`, `.env`. Thấy lỗi thì ghi vào báo cáo; Claude sẽ sửa.
- **Không in secret.** Trước khi dán output, kiểm chắc output không chứa `BINGX_API_SECRET`.

## 1. Mục tiêu kiểm chứng

1. **Chữ ký POST đặt lệnh đúng.** Đợt 112 mới kiểm thật GET và DELETE, chưa kiểm POST.
2. Trọn vòng **đặt → đọc trạng thái → huỷ → xác nhận đã huỷ** chạy đúng trên sàn, kết thúc với exit 0.
3. **Định dạng phản hồi thật** khớp với những gì code đang giả định, gồm:
   - tên và kiểu của `orderId`;
   - chuỗi trạng thái sau khi đặt: `NEW` hay `PENDING`;
   - chuỗi trạng thái sau khi huỷ: `CANCELED` hay `CANCELLED`;
   - có trường `executedQty` không;
   - `data` có bọc trong `order` hay không.

## 2. Các bước

1. **Trạng thái trước khi chạy** (chỉ đọc, dùng `BingXClient` với `base_url` demo trong một script tạm **ngoài repo**): in số dư VST, số lệnh chờ BTC-USDT, số vị thế BTC-USDT.
   → **Kỳ vọng:** 0 lệnh chờ, 0 vị thế. Nếu khác thì **dừng lại và báo**.

2. **Chạy khô:**
   ```
   uv run python scripts/bingx_drill_place_cancel.py --symbol BTC-USDT --env demo
   ```
   → **Kiểm chứng bằng:** dán nguyên văn output. Môi trường phải là `DEMO (DEMO VST)`.

3. **Chạy thật trên demo.** Script hỏi `YES` qua `input()`, nên truyền `YES` qua stdin:
   ```
   echo YES | uv run python scripts/bingx_drill_place_cancel.py --symbol BTC-USDT --env demo --send
   ```
   Trên PowerShell dùng `"YES" | uv run python ...`. Ghi lại **exit code** (`$LASTEXITCODE` hoặc `$?`).
   → **Kiểm chứng bằng:** dán nguyên văn output kèm exit code.
   - **Kỳ vọng:** exit 0, có dòng "ĐÃ XÁC NHẬN HUỶ THÀNH CÔNG".
   - **Nếu exit khác 0:** không chạy lại, sang bước 4, rồi báo cáo đúng thông điệp CRITICAL mà script in ra.

4. **Trạng thái sau khi chạy.** Dùng script tạm như bước 1, và thêm việc gọi `BingXTradeClient(base_url=demo).get_order` với `order_id` in ra ở bước 3. In **nguyên văn `raw`** của lệnh (không có secret trong đó).
   → **Kỳ vọng:** 0 lệnh chờ, 0 vị thế, lệnh ở trạng thái đã huỷ.
   - Nếu có vị thế mở (lệnh bị khớp): **không** tự đóng. Báo lại, Claude quyết.

5. **Đối chiếu định dạng.** Lập bảng `Trường | Code đang giả định | Sàn thật trả về | Khớp?` cho 5 điểm ở §1 mục 3. Lấy số liệu từ `raw` ở bước 4 và từ output bước 3.

6. **Xoá mọi script tạm** ngoài repo.
   → **Kiểm chứng bằng:** `git status --short` chỉ còn các file đã có từ trước.

## 3. Báo cáo cho Claude

Báo cáo gồm các phần sau, theo thứ tự:
1. Kết luận một dòng: "Diễn tập demo đạt, exit 0" hoặc "Không đạt, exit X, lý do …".
2. Output bước 1–4 nguyên văn.
3. Bảng đối chiếu định dạng ở bước 5.
4. Mọi điều bất thường, kể cả cảnh báo nhỏ.

Kết thúc bằng câu: "Tôi chỉ chạy trên demo VST, không chạy --env live, không sửa code, không in secret."
