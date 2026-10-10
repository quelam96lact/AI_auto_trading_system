# Brief đợt 179 — Triển khai collector có bản sửa đối soát đợt 176

Ngày: 10/10/2026 (thứ Bảy, không có phiên). Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push, KHÔNG sửa code**.
Chủ dự án đồng ý triển khai ngày 10/10.

## 0. Vì sao
Commit `6601484` (đợt 176) sửa `trading/collector/account_sync.py`: đối soát lệnh thật đọc lịch sử lệnh qua `trading/ssi_orders.fetch_order_history`, để đọc đúng `filledQty`/`cancelQty`. Container `collector` đang chạy được build từ trước commit đó (Up ~4 giờ lúc 18:20), nên **vẫn chạy code cũ**. Đợt này chỉ build lại và khởi động lại **riêng collector**.

## 1. Việc làm
1. **Trước khi làm:**
   - `git log --oneline -1` phải là `dc33fb4` hoặc mới hơn;
   - `git status --short` phải sạch;
   - ghi lại `docker compose ps` và giờ hiện tại (giờ VN). Gọi giờ này là T0.

   → **kiểm chứng bằng:** dán output.
2. **Build và khởi động lại:** `docker compose up -d --build collector`. **Chỉ collector.** Không `down`, không đụng `engine`, `postgres`, `nats`, `grafana`, `nats-test`.

   → **kiểm chứng bằng:** `docker compose ps` cho thấy collector "Up" vài giây hoặc vài phút, các service khác giữ nguyên thời gian Up như trước.
3. **Code mới đã vào container:**
   ```
   docker compose exec collector python -c "import inspect, trading.collector.account_sync as a; print('fetch_order_history' in inspect.getsource(a._reconcile_real_orders))"
   ```
   → in `True`.
4. **Đồng bộ tài khoản vẫn chạy:** chờ tối đa 12 phút (vòng đồng bộ 5 phút/lần), rồi chạy:
   ```
   docker compose exec postgres psql -U trading -d trading -c "select account_no, max(ts) at time zone 'Asia/Ho_Chi_Minh' from account_balance_snapshot group by 1"
   ```
   → **kiểm chứng bằng:** cả `0434226` và `0434221` có `max(ts)` **sau T0**.
5. **Không lỗi:**
   ```
   docker compose logs --since <T0> collector 2>&1 | grep -iE "traceback|error|account sync failed|derivative sync failed"
   ```
   → rỗng. Có dòng nào thì dán nguyên văn và **dừng**, không tự sửa.
6. **Bảng lệnh thật vẫn rỗng** (đối soát không có gì để làm, đúng như kỳ vọng):
   ```
   docker compose exec postgres psql -U trading -d trading -c "select status, count(*) from real_order_fills group by 1"
   ```
   → 0 dòng.

## 2. Phạm vi
- **Chỉ được chạy:**
  - các lệnh `docker compose` ở §1 cho service `collector`;
  - lệnh `exec`/`psql` chỉ đọc;
  - `git log`/`git status`.
- **Cấm:**
  - sửa bất kỳ file nào;
  - `docker compose down`, `restart`/`build` service khác;
  - xóa volume hay image;
  - ghi DB;
  - chạy `scripts/sched.sh`;
  - chạy `scripts/drill_place_cancel_order.py`;
  - in token, khóa hay mật khẩu ra màn hình (không `cat .env`, không đọc `.ssi_sdk_token.json`).
- Nếu build lỗi: dán output, **dừng**. Container cũ vẫn chạy khi build hỏng, không cố khởi động lại bằng cách khác.

## 3. Hoàn thành khi
- Bước 3 in `True`.
- Bước 4: cả hai tài khoản có snapshot sau T0.
- Bước 5 rỗng. Bước 6: 0 dòng.
- `docker compose ps` cuối cùng: mọi service Up, chỉ collector có thời gian Up mới.

## 4. Báo cáo cho Claude
Output nguyên văn của từng bước §1 (T0, `ps` trước/sau, `True`, bảng snapshot, kết quả grep log, bảng `real_order_fills`), và mọi điều bất thường.
