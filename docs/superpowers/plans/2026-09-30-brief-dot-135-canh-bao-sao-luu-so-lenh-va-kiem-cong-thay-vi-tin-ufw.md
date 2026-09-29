# Brief đợt 135 — không ai canh bản sao lưu sổ lệnh, và phép kiểm tường lửa có thể báo đèn xanh giả

**Base commit:** `e37f6bc`.
**Người thực thi:** agent — **trọn bộ việc 1–2**. **Claude:** audit, commit, push.

---

## §0. Bối cảnh — hai lỗ Claude tự ghi nhận khi audit đợt 132–133

Cả hai cùng một họ: **bên kiểm không phủ hết thứ bên sản xuất tạo ra**, nên hỏng thì im lặng.

### Lỗ 1 — `backup_check.py` không thấy bản sao lưu sổ lệnh

`scripts/backup_check.py:207` chỉ tìm `trading_*.dump` và `trading_*.sql.gz`, tức **chỉ bản sao lưu DB**. Đợt 132 thêm job `orderbook-backup` sinh ra `orderbook_*.tar.gz` mà **không mở rộng bên kiểm**. Job đó hỏng âm thầm nhiều tuần thì không cảnh báo nào nổ. Bất đối xứng do chính đợt 132 tạo ra, và audit đợt đó của Claude không bắt được.

### Lỗ 2 — `ufw` không chi phối cổng do Docker publish

Agent đợt 133 tự nêu, Claude xác nhận: Docker chèn luật iptables riêng và **đi vòng qua `ufw`**. Nên phép kiểm số 7 của `host_preflight.py` có thể báo **ĐẠT** trong khi Postgres thật sự lộ ra internet — chỉ cần một dòng `ports:` bị đổi thành `0.0.0.0:5432:5432`. Đây đúng là **đèn xanh giả**, thứ mà chính đợt 133 sinh ra để diệt.

**Hiện chưa có rủi ro thật:** Claude đã đối chiếu, cả bốn dòng `ports:` đang bind `127.0.0.1` (5432, 4222, 4223, 3000). Việc này là **bịt trước**, không phải chữa cháy.

---

## §1. Việc 1 — `backup_check.py` canh cả bản sao lưu sổ lệnh

### Ngưỡng tuổi PHẢI theo lịch giao dịch, không được dùng lại 23 giờ

Đây là chỗ duy nhất dễ làm sai, và làm sai thì thành **báo động giả mỗi cuối tuần** — đúng thứ đợt 131 và 132 đã mất hai lượt để dọn.

Lý do: sổ lệnh chỉ sinh ra vào **ngày giao dịch**. Job `orderbook-backup` chạy 02:30 **hằng ngày**, nhưng chỉ tạo file khi có dữ liệu mới. Hệ quả, tuổi hợp lệ của bản mới nhất lúc `backup-check` chạy (03:00):

| Lúc kiểm | Bản mới nhất được tạo | Tuổi hợp lệ |
|---|---|---|
| thứ Ba 03:00 | thứ Ba 02:30 (gói dữ liệu thứ Hai) | ~0,5 giờ |
| Chủ nhật 03:00 | thứ Bảy 02:30 (gói dữ liệu thứ Sáu) | ~24,5 giờ |
| **thứ Hai 03:00** | **thứ Bảy 02:30** | **~48,5 giờ** |
| sau tuần nghỉ Tết | trước kỳ nghỉ | **có thể hơn 8 ngày** |

Một ngưỡng cố định **không thể** đúng cả bốn dòng.

**Quy tắc phải dùng:** gọi `trading.calendar_vn.previous_trading_day` (và `holidays` từ `config/config.yaml`) để lấy ngày giao dịch gần nhất **trước hôm nay**, gọi nó là `D`. Bản sao lưu sổ lệnh mới nhất phải có `mtime` **sau khi phiên ngày `D` kết thúc** (14:46 giờ VN). Thiếu thì báo CRITICAL, nêu rõ `D` và tuổi thực tế.

Kiểm lại logic với chính bảng trên: thứ Hai 03:00 → `D` = thứ Sáu → đòi `mtime` sau thứ Sáu 14:46 → bản thứ Bảy 02:30 **đạt**. Nếu job thứ Bảy hỏng, bản mới nhất là của thứ Sáu 02:30 (dữ liệu thứ Năm) → **trước** thứ Sáu 14:46 → **báo đúng**.

**Claude đã mở ra xem trước khi thiết kế** (bài học [[kiem-dinh-nghia-cua-moc-truoc-khi-dung]] — hai lần trong dự án này tái dùng một hàm mà không đọc nó làm gì). `trading/calendar_vn.py:55-63`:

> `"""Ngay giao dich gan nhat TRUOC d (khong gom d), bo qua cuoi tuan va ngay le."""`
> `cur = d - timedelta(days=1)` rồi lùi tiếp tới khi `is_trading_day(cur)`.

Đúng là **không gồm `d`**, nên quy tắc trên chạy được. Agent vẫn phải tự đối chiếu và trích lại trong báo cáo — đừng tin đoạn trích này.

### Các phép kiểm cho bản sao lưu sổ lệnh

1. **Có tồn tại** `orderbook_*.tar.gz` nào không.
2. **Tuổi** theo quy tắc trên.
3. **Toàn vẹn**: `tar -tzf` đọc được và số file bên trong > 0. Trên Windows cần `--force-local` (đường dẫn `D:/...` bị `tar` hiểu là `host:path` — đợt 134 đã đo).
4. **KHÔNG kiểm kích thước tối thiểu.** Một phiên mà bộ ghi chết sớm để lại file 0,26 MB vẫn là bản sao lưu **đúng** của dữ liệu đã có; chất lượng dữ liệu là việc của `orderbook-daily-check` (nó đã bắt được đúng ca 29/09). Thêm ngưỡng kích thước ở đây sẽ báo trùng và báo oan.

### Giữ nguyên phần DB

Không đổi một dòng nào của logic bản sao lưu DB: ngưỡng **23 giờ** và phép tính của nó đã có chú thích và **test ghim** (`test_mot_dem_backup_hong_PHAI_bi_bat_voi_nguong_MAC_DINH`). Hai loại sao lưu có hai quy tắc khác nhau vì bản chất khác nhau — ghi rõ điều đó trong chú thích để không ai gộp lại.

### Cổng

- Test cho từng phép trên, **và** cho đủ bốn dòng của bảng lịch (thứ Ba, Chủ nhật, thứ Hai, sau kỳ nghỉ dài) bằng thời điểm giả. Dòng **thứ Hai** là quan trọng nhất: phải **im lặng**.
- Test "job thứ Bảy hỏng" → phải **báo**.
- **Phá thử:** thay quy tắc lịch bằng ngưỡng cố định 23 giờ → test thứ Hai và test Chủ nhật phải **đỏ**. Dán thông điệp nguyên văn.
- Mọi test DB sẵn có phải **xanh y nguyên**, không sửa một dòng.
- Chạy thật `--dry-run` trên `_backups/db` (đang có `orderbook_20260930.tar.gz` và hai bản dump): phải **im**, thoát 0. Rồi chạy trên một thư mục tạm **chỉ có bản dump DB, không có bản sổ lệnh**: phải **báo** thiếu sao lưu sổ lệnh. Dán cả hai, nguyên văn.

---

## §2. Việc 2 — `host_preflight.py`: kiểm THẲNG cổng, đừng chỉ tin `ufw`

Thêm phép kiểm thứ **12**, theo đúng khuôn các phép có sẵn (`_check_*` trả `Result`, sự kiện lấy trong `collect_facts`, ba trạng thái).

**Nội dung:** mọi cổng được publish phải bind `127.0.0.1`. Bất kỳ cổng bind `0.0.0.0`, `::`, hoặc không ghi địa chỉ (mặc định = mọi giao diện) là **HỎNG**, nêu rõ service và cổng nào.

**Nguồn sự kiện — thứ tự ưu tiên, và đây là phần cần cẩn thận:**
1. `docker compose config` (đã gộp cả `docker-compose.override.yml`). Đây là **sự thật**: trên VPS §11 Bước 5 tạo một file override, nên chỉ đọc `docker-compose.yml` sẽ bỏ sót.
2. Nếu không gọi được `docker compose` (Docker chưa chạy): **đọc trực tiếp** `docker-compose.yml` cộng các file override có mặt, và **ghi rõ trong phần chi tiết** rằng đọc từ file chứ không qua compose.

**Không được ra `BỎ QUA` chỉ vì Docker chưa chạy** — file YAML vẫn đọc được, và đây là phép kiểm an ninh. Chỉ `BỎ QUA` khi **không** đọc được cả compose lẫn file nào (nêu lý do).

**Sửa luôn cách diễn đạt của phép kiểm số 7** (`_check_ufw`): thêm vào phần chi tiết một câu nói rõ `ufw` **không** chi phối cổng do Docker publish, và trỏ sang phép kiểm số 12. Một dòng "ĐẠT" của ufw không được để người đọc hiểu là "cổng đã kín".

**Cổng:**
- Test: tất cả bind `127.0.0.1` → ĐẠT; một cổng `0.0.0.0` → HỎNG nêu đúng service; cổng không ghi địa chỉ → HỎNG; đọc được từ file khi compose vắng → vẫn ĐẠT/HỎNG kèm ghi chú nguồn; không đọc được gì → BỎ QUA kèm lý do.
- **Phá thử:** cho phép kiểm luôn trả ĐẠT → test `0.0.0.0` đỏ. Cho nó BỎ QUA khi Docker vắng → test "đọc từ file" đỏ.
- **Chạy thật** `scripts/sched.sh host-preflight` trên máy này: phép 12 phải **ĐẠT** (bốn cổng đang bind `127.0.0.1`), và tổng kết thành **5 ĐẠT / 0 HỎNG / 8 BỎ QUA**. Dán bảng nguyên văn.
- **Đối chứng âm tính:** tạm đổi một dòng `ports:` trong một **bản sao** `docker-compose.yml` ở thư mục tạm thành `0.0.0.0:5432:5432`, chạy phép kiểm trên bản sao đó, phải ra **HỎNG**. **Không** sửa `docker-compose.yml` thật.

---

## §3. Tiêu chí chung

```
uv run pytest -q   (TOÀN BỘ, nats-test chạy)   → ≥ 1.520 passed + test mới, 0 failed
uv run ruff check trading tests scripts        → sạch
uv run pytest tests/test_deployment_doc.py      → xanh
docker compose config -q                        → sạch
```

`npx gitnexus detect-changes --repo AI_auto_trading_system` ở cuối (MCP đang hỏng, dùng CLI).

## §4. Phạm vi

**Được sửa:** `scripts/backup_check.py`, `tests/test_backup_check.py`, `scripts/host_preflight.py`, `tests/test_host_preflight.py`; `DEPLOYMENT.md` (**chỉ** câu mô tả hai phép kiểm mới, nếu cần); báo cáo `docs/superpowers/research/2026-09-30-dot-135-canh-bao-sao-luu-so-lenh-va-kiem-cong.md`.

**KHÔNG được đụng:** `trading/` (chỉ **import** `calendar_vn`); `scripts/backup_db.sh`, `scripts/backup_orderbook.sh`, `scripts/disk_check.py`, `scripts/container_health_check.py`, `scripts/sched.sh`, `docker-compose.yml`, `.githooks/`, `config/`; **logic và test của bản sao lưu DB** trong `backup_check.py`; test của đợt khác; `.env` thật; `data/orderbook/`; mọi container đang chạy.

## §5. Điều cấm

- **Không commit, không push.** Không rebuild, không restart container.
- Không sửa `docker-compose.yml` thật (đối chứng âm tính dùng **bản sao** ở thư mục tạm).
- Không gửi Telegram thật: `--dry-run` hoặc hàm gửi giả.
- Không đọc giá trị trong `.env`; không kết nối SSI; không đặt lệnh; không `--send`.
- Không xoá/sửa file nào trong `_backups/` hay `data/orderbook/` (chỉ **đọc**).
- Cấm `git checkout`, `git restore`, `git stash` (trừ `git stash create`).
- Không tạo/sửa/xoá scheduled task.
- **Không chạy `merge_bars_daily_chunks.py` với DSN của DB `trading`** (việc của Claude thứ Bảy).

## §6. Báo cáo phải có

1. Việc 1: bảng test ↔ phép kiểm, **bốn dòng bảng lịch** với kết quả từng dòng, phá thử "thay bằng 23 giờ" với thông điệp đỏ nguyên văn, và hai lần chạy thật `--dry-run`.
2. Việc 1: trích `previous_trading_day` để chứng minh nó trả ngày **trước** `d`, không phải chính `d`.
3. Việc 2: bảng test ↔ trường hợp, hai phá thử, bảng `host-preflight` chạy thật (kỳ vọng 5 ĐẠT / 0 HỎNG / 8 BỎ QUA), và đối chứng âm tính `0.0.0.0` trên bản sao.
4. Những gì **không** kiểm được, và vì sao.
5. Chỗ nào brief sai hoặc mơ hồ. **Nếu brief đảo một quyết định có chủ ý nào** (đọc chú thích trước khi sửa, nhất là ngưỡng 23 giờ của bản sao lưu DB), **báo ngay**.
