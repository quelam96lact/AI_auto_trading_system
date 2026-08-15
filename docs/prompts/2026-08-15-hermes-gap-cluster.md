# NHIỆM VỤ: Giải thích cụm ±25–35% trong 422 bước nhảy còn dư (chỉ đọc)

Repo: `D:\My_Vault_Obsidian\Project\AI_auto_trading_system`, nhánh `feature/data-layer`, base `bfd00c9`.

Tiếp nối `bfd00c9`. Công việc lần trước đã commit và push — đọc commit message đó trước.

## Câu hỏi DUY NHẤT cần trả lời

Phần dư 422 sự kiện (cột `cause = khong_giai_thich_duoc` trong
`scripts/research_gap_causes.csv`) **không phân bố ngẫu nhiên**:

```
283/422 có tỉ lệ trong [1,25 ; 1,35]      đỉnh ở 1,33 · 1,32 · 1,26
 65/422 có tỉ lệ trong [0,65 ; 0,75]
 → 82% nằm trong dải ±25–35%
```

Biên độ tối đa của sàn VN là ±15%/phiên (UPCoM), ±10% (HNX), ±7% (HOSE). **Một phiên
không thể nhảy 30%.** Mà nhóm này đã bị loại nhóm "bar thiếu" và "trở lại sau đình chỉ"
rồi. Vậy còn đúng hai khả năng:

- **(A) Bộ đếm ngày mở cửa còn sót** — hai dòng liền nhau trong DB thực ra KHÔNG phải
  hai phiên liền nhau. Có thể do `trading/calendar_vn.py` thiếu ngày nghỉ, hoặc mã ngừng
  giao dịch ngắn dưới ngưỡng 10 ngày mà bộ đếm không bắt, hoặc SSI bỏ hẳn phiên không có
  khớp lệnh nên DB không bao giờ có dòng đó.
- **(B) Có cơ chế giá khác** mà ta chưa biết: biên độ rộng ngày giao dịch trở lại, đấu
  giá, chuyển sàn, đổi mã.

Trả lời được (A) hay (B) — bằng dữ liệu, không bằng suy đoán — là xong nhiệm vụ.

## Cách kiểm rẻ nhất (làm đúng cái này trước, đừng làm to hơn)

1. Lấy **10 sự kiện** trong cụm chặt nhất (tỉ lệ 1,32–1,335) từ
   `scripts/research_gap_causes.csv`.
2. Với mỗi sự kiện, gọi SSI lấy **toàn bộ phiên trong ±10 ngày** quanh ngày bước nhảy —
   cửa sổ RỘNG, không phải cửa sổ hẹp như lần trước. Dùng lại
   `scripts/verify_ssi_gaps.py --window 10`, đã có sẵn, đừng viết lại.
3. Câu hỏi cụ thể: **SSI có trả phiên nào mà DB không có, nằm GIỮA hai dòng tạo ra bước
   nhảy không?**
   - CÓ → khả năng (A). Nói rõ ngày nào bị thiếu, và truy vì sao đường ingest bỏ sót
     (backfill bỏ qua? phân trang? hay SSI trả nhưng parser bỏ?).
   - KHÔNG → khả năng (B). Khi đó xem `cal_days` và lịch giao dịch: hai phiên có thật sự
     liền nhau không, và mức nhảy so với biên độ sàn tương ứng là bao nhiêu.

Nếu 10 mẫu cho kết quả nhất quán thì DỪNG, kết luận, không cần quét cả 422. Nếu lẫn lộn
thì nói rõ tỉ lệ mỗi loại rồi mới bàn tiếp.

## Ràng buộc — giống lần trước, không đổi

- Postgres đang phục vụ `collector` + `engine` chạy LIVE. **CHỈ ĐỌC.** Không
  `UPDATE`/`DELETE`/`INSERT` vào bảng hệ thống.
- Token SSI đọc từ `ssi_auth_state`; token hết hạn thì DỪNG và báo, không tự làm OTP.
- Không đụng `trading/engine/`, `trading/real_orders.py`, `scripts/confirm_real_order.py`,
  `config/config.yaml`. Nếu phát hiện bug ở `trading/collector/backfill.py` thì **BÁO CÁO
  kèm test tái hiện, ĐỪNG tự sửa** — đó là code đang chạy production.
- KHÔNG commit, KHÔNG push.
- DSN dùng `127.0.0.1`; script mới nhớ `sys.stdout.reconfigure(encoding="utf-8")`;
  `git diff --stat` sau mỗi Edit vì hook formatter reformat cả file.

## Báo cáo cuối

1. Bảng 10 mẫu: ngày bước nhảy | số phiên SSI trả | số phiên DB có | có phiên nào SSI có
   mà DB không có, nằm giữa hai dòng đó không.
2. Kết luận (A) hay (B), kèm bằng chứng. Nếu (A): ngày thiếu cụ thể + nguyên nhân ở đường
   ingest. Nếu (B): cơ chế giá nào, dựa trên gì.
3. Output thật của `pytest -m "not integration"` và ruff (8 lỗi pre-existing để nguyên).
4. Xác nhận không có câu lệnh ghi nào chạm bảng hệ thống.

Nếu kết luận là "không xác định được từ 10 mẫu này" thì nói thẳng như vậy — nói không biết
rẻ hơn nhiều so với một kết luận sai phải đi đính chính, và trong dự án này đã phải đính
chính hai lần rồi.
