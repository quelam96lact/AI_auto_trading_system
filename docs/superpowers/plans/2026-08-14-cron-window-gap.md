# Kế hoạch: lịch cron chặn mất cảnh báo token trước giờ mở cửa

Ngày giao: 2026-08-14 tối. Nhánh: `feature/data-layer`. Base: `5490348`.

**KHÔNG commit, KHÔNG push.** Việc này **chỉ sửa `DEPLOYMENT.md`** — không đụng
code, không đụng container.

---

# Lỗ hổng

`7700992` thêm cảnh báo 2B (token SSI sắp/đã hết hạn). Nó có nhánh riêng cho
khung **8:00–9:00** ngày giao dịch, đặt ra chính xác để báo **trước giờ mở cửa**
— vì sự cố 14/08 là token chết giữa phiên và không ai biết cho tới khi soi log.

`scripts/heartbeat_check.py` (nhánh gate trong `main()`):

```python
if not is_trading_time(now) and not (
    time(8, 0) <= now.astimezone(TZ).time() < time(9, 0)
    and now.astimezone(TZ).weekday() < 5
):
    return 0
```

Nhưng `DEPLOYMENT.md` §9 dòng 154 ghi lịch cron:

```
*/5 9-15 * * 1-5
```

`9-15` là **giờ 9 đến 15**. Khung 8:00–8:59 **không bao giờ được gọi**. Nhánh
tiền-phiên là code chết trong triển khai.

Chúng ta xây một cái chuông rồi treo ngoài tầm với: code đúng, test xanh, triển
khai vô hiệu.

---

# Phải làm

## 1. Sửa dòng cron

`9-15` → `8-15`. Giữ nguyên mọi phần còn lại của dòng (đường dẫn, `set -a`,
`DB_DSN`, redirect log).

## 2. Sửa phần lý do đã lỗi thời ngay trên đó

Comment hiện tại viết:

```
# thêm (chỉ chạy trong giờ giao dịch VN, script tự bỏ qua ngoài phiên):
```

Câu này ĐÚNG khi viết (script chỉ làm việc trong `is_trading_time`), nhưng
`7700992` đã thêm khung tiền-phiên nên nó không còn đúng. Sửa cho khớp thực tế:
script làm việc trong giờ giao dịch **và** khung 8:00–9:00 ngày giao dịch.

## 3. Ghi rõ script giờ kiểm những gì

§9 hiện chỉ nói về heartbeat. Sau `7700992` và `d775ebb`, script kiểm **bốn**
thứ. Liệt kê ngắn gọn, mỗi thứ một dòng, kèm commit:

- service ngừng heartbeat (bản gốc)
- dữ liệu ngừng chảy — bar không về trong 9:00–11:30 / 13:00–14:30 (`7700992`)
- token SSI sắp/đã hết hạn — gồm khung 8:00–9:00 (`7700992`)
- hai sổ sách lệch: `cash + Σ(avg_price×qty) − CAPITAL == realized_pnl` (`d775ebb`)

## 4. Thêm bước kiểm chứng cho cảnh báo tiền-phiên

§9 đã có một bước kiểm chứng cho heartbeat (`docker compose stop engine`, đợi
>5 phút). Thêm một bước tương đương cho 2B, vì đây chính là nhánh vừa suýt chết:

Gợi ý — bạn tự viết cho gọn và đúng: xác nhận cron thật sự chạy lúc 8:xx (ví dụ
xem `/var/log/trading-heartbeat.log` có dòng trong khung đó vào một ngày giao
dịch). **KHÔNG** hướng dẫn cách giả mạo thời gian hệ thống trên máy sản xuất.

---

# Ràng buộc

- **CHỈ** sửa `DEPLOYMENT.md`. Không đụng `scripts/heartbeat_check.py` — code đã
  đúng, chỉ có lịch sai.
- Không đụng container, không chạy `docker compose`.
- Giữ nguyên văn phong và ngôn ngữ hiện có của file.
- **KHÔNG** thay đổi `HEARTBEAT_MAX_AGE_SECONDS` hay bất kỳ ngưỡng nào.

# Kiểm chứng

1. `grep -n "8-15" DEPLOYMENT.md` → thấy dòng cron mới; `grep -n "9-15"` →
   không còn dòng cron nào dùng `9-15`.
2. Rà **toàn bộ repo** xem còn chỗ nào khác chép lại lịch cron cũ không
   (`grep -rn "9-15" .`). Nếu có, **báo cáo** — đừng tự sửa file ngoài phạm vi.
3. `uv run pytest -q` → 304 passed (không đụng code, số phải y nguyên).
4. `git diff --stat` → đúng 1 file.

# Nếu thấy kế hoạch sai

Dừng và phản biện. Hai chỗ đáng nghi:

1. **`8-15` có đủ không?** Phiên chiều đóng 14:45, nhưng cảnh báo 2A cắt ở
   14:30 và 2B chạy hết `is_trading_time` (tới 14:45). Giờ 15 vẫn nằm trong
   lịch cũ nên tôi giữ. Nếu bạn thấy nên thu lại hoặc nới ra — nói ra kèm lý do.
2. **Có nên chạy cả ngoài giờ không?** Cảnh báo 2C (lệch sổ sách) là kiểm tra
   tính ĐÚNG ĐẮN, về lý thuyết đáng chạy 24/7 chứ không chỉ trong phiên. Tôi cố
   ý KHÔNG mở rộng vì nó làm tăng nguy cơ báo láo ban đêm khi engine đang ghi
   dở trạng thái. Nếu bạn thấy lập luận này sai — nói ra, đừng tự mở rộng.
