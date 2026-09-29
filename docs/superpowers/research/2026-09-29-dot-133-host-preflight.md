# Báo cáo đợt 133 — `host_preflight.py`, giới hạn log trong repo, nối lịch

Không commit, không push, không sửa gì trên host, không restart container, không đọc/in giá trị `.env`.

## 1. Việc 1 — `scripts/host_preflight.py`

Hàm quyết định thuần `evaluate(facts, sched_jobs)`; phần đọc host là `collect_facts` (chỉ đọc). Ba trạng thái `ĐẠT` / `HỎNG` / `BỎ QUA` (kèm lý do). **Khoá thiếu trong sự kiện cũng ra `BỎ QUA`, không bao giờ `ĐẠT`.** Tập job suy từ chính `sched.sh` (không viết cứng số). Mã thoát 0 / 1 (có HỎNG) / 2 (không đọc được repo). `--json` có.

### Bảng test ↔ phép kiểm (`tests/test_host_preflight.py`, 44 test)

| # | Phép kiểm (đọc gì) | ĐẠT | HỎNG | BỎ QUA |
|---|---|---|---|---|
| 1 | `TRADING_BACKUP_DIR` (biến môi trường, không đọc `.env`) | tất cả tốt | thiếu biến / không tồn tại / không ghi được | — |
| 2 | `crontab -l` đủ job của `sched.sh` + `CRON_TZ` | ✔ | thiếu job (nêu tên) / thiếu `CRON_TZ` / job chỉ nằm trong dòng comment / chưa có crontab | ✔ không có `crontab` |
| 3 | `/etc/docker/daemon.json` | ✔ | thiếu `log-opts`, thiếu `max-file`, không có file | ✔ không đọc được (quyền) |
| 4 | `/etc/logrotate.d/trading` | ✔ | không có | ✔ |
| 5a | `.env` mode 600 | ✔ | mode sai / thiếu file | ✔ (Windows) |
| 5b | `.env` đếm `\r` | ✔ | ≥1 `\r` (chỉ in số đếm) | — |
| 6 | múi giờ | ✔ | sai | ✔ |
| 7 | `ufw status` | ✔ | tắt; 5432 hoặc 3000 mở cho `Anywhere` | ✔; (mở cho một IP cụ thể **không** hỏng) |
| 8 | đĩa (trống ≥10 GB, tổng ≥40 GB) | ✔ | thiếu chỗ / tổng nhỏ | ✔ |
| 9 | cờ thực thi `scripts/*.sh`, `.githooks/pre-push` | ✔ | thiếu (nêu tên file) | ✔ (Windows) |
| 10 | `config.yaml: real_trading_enabled` | ✔ | `true` / không thấy khoá | ✔ |
| 11 | đồng bộ đồng hồ (`timedatectl`) | ✔ | không đồng bộ | ✔ |

Chống báo đẹp: `test_su_kien_thieu_khong_bao_dat`, `test_khong_do_duoc_gi_ca_thoat_0_nhung_canh_bao_ro`, `test_skip_khong_bi_dem_la_dat`, `test_bo_qua_khong_lam_thoat_khac_0`. Thêm `test_main_json_hop_le_va_khong_lo_gia_tri_env` (giá trị và tên biến trong `.env` không xuất hiện trong đầu ra).

### Phá thử (thông điệp đỏ nguyên văn)

1. Bỏ nhánh `HỎNG` của phép kiểm đồng hồ (luôn `ĐẠT`):
   `FAILED tests/test_host_preflight.py::test_clock_khong_dong_bo_hong` — `AssertionError: assert 'ĐẠT' == 'HỎNG'` (1 failed, 43 passed).
2. Cho `BỎ QUA` trả `ĐẠT`: **12 test đỏ**, gồm `test_khong_do_duoc_gi_ca_thoat_0_nhung_canh_bao_ro`, `test_skip_khong_bi_dem_la_dat` và 10 test `*_bo_qua`; thông điệp: `AssertionError: assert 'ĐẠT' == 'BỎ QUA'`.
Cả hai đã khôi phục; 44 passed.

### Chạy thật trên máy này (Windows) — nguyên văn

Chạy trực tiếp `uv run python scripts/host_preflight.py` (biến `TRADING_BACKUP_DIR` chưa được nạp từ `.env` nên phép 1 ra `HỎNG` — đúng, vì công cụ đọc môi trường, không đọc `.env`; EXIT=1). Chạy qua `scripts/sched.sh host-preflight` (nạp `.env`), EXIT=0:

```
TRẠNG THÁI PHÉP KIỂM                                                      CHI TIẾT
ĐẠT      TRADING_BACKUP_DIR có mặt, thư mục tồn tại và ghi được         D:/My_Vault_Obsidian/Project/_backups/db
BỎ QUA   crontab có đủ job của sched.sh và CRON_TZ                      không có lệnh crontab trên hệ này
BỎ QUA   /etc/docker/daemon.json giới hạn log (max-size, max-file)      không phải Linux (daemon.json của máy chủ nằm ở /etc/docker)
BỎ QUA   /etc/logrotate.d/trading tồn tại                               không phải Linux (không có logrotate)
BỎ QUA   .env mode 600                                                  không phải Linux (Windows không có mode 600)
ĐẠT      .env không có ký tự \r                                         0 ký tự \r
BỎ QUA   múi giờ hệ thống Asia/Ho_Chi_Minh                              không có timedatectl hay /etc/timezone trên hệ này
BỎ QUA   ufw bật, Postgres 5432 / Grafana 3000 không mở ra ngoài        không có ufw trên hệ này
ĐẠT      đĩa: trống ≥ 10 GB và tổng ≥ 40 GB                             trống 186.0 GB / tổng 449.2 GB
BỎ QUA   scripts/*.sh và .githooks/pre-push thực thi được               không phải Linux (Windows không có bit thực thi)
ĐẠT      config.yaml: real_trading_enabled: false                       false
BỎ QUA   đồng hồ hệ thống đồng bộ                                       không có timedatectl hay /etc/timezone trên hệ này

Tổng kết: 4 ĐẠT, 0 HỎNG, 8 BỎ QUA
Lưu ý: 8 phép kiểm BỎ QUA chưa được xác nhận — không tính là ĐẠT.
EXIT=0
```

(dòng đồng hồ trong log ghi "không có timedatectl trên hệ này"; văn bản trên chép từ log.)

## 2. Phép kiểm KHÔNG kiểm được trên Windows

crontab, daemon.json, logrotate, mode 600, múi giờ, ufw, cờ thực thi, đồng bộ đồng hồ — 8 phép, vì các cơ chế đó (cron, `/etc`, `ufw`, `systemd`, bit thực thi) không tồn tại trên Windows. Tất cả ra `BỎ QUA` kèm lý do, **không** ra `ĐẠT` (xem bảng thật ở trên). Chưa kiểm được trên Linux thật.

## 3. Việc 2 — giới hạn log trong `docker-compose.yml`

Thêm neo `x-logging: &default-logging` (`json-file`, `max-size: "10m"`, `max-file: "3"`) và `logging: *default-logging` cho **cả 6 service** (14 dòng thêm). `docker compose config -q` sạch; `docker compose --profile test config` hiển thị `max-size: 10m` ở `collector, engine, grafana, nats, nats-test, postgres`. Mức thực tế nhỏ (~0,25 GB/năm ngoài giờ phiên) — việc dọn cho gọn, không phải chữa cháy.

**Giới hạn chỉ có hiệu lực sau khi container được TẠO LẠI** (`docker compose up -d`); chưa restart container nào. `DEPLOYMENT.md` §8 giờ ghi khối trong repo là lớp chính, `daemon.json` là lớp phụ.

## 4. Việc 3 — nối lịch

`sched.sh`: thêm case `host-preflight` (qua `run_if_docker_up.sh`), chú thích đầu file và dòng `dung:` đủ **15** job. `DEPLOYMENT.md`: §8, §9 (job 14: Chủ nhật 07:00 hằng tuần, kèm lý do), bảng Windows, và đoạn "chạy `host-preflight` ngay sau Bước 8" ở §11. `tests/test_deployment_doc.py` xanh (3 passed).

## 5. Scheduled task Windows đề xuất (chưa tạo)

`trading-host-preflight` — Chủ nhật 07:00 hằng tuần, `wscript.exe //B //Nologo ...\run_hidden.vbs host-preflight`. Trên Windows nó chủ yếu ra `BỎ QUA`; giá trị thật là trên VPS.

## 6. Kiểm chung

`uv run pytest -q` → **1520 passed**; `ruff check trading tests scripts` sạch; `docker compose config -q` sạch; `bash -n scripts/sched.sh` sạch; `git ls-files -s scripts/sched.sh` = 100755; `detect_changes`: risk low, 0 process.

## 7. Không kiểm được / brief mơ hồ

- Chưa chạy trên Linux/VPS thật; các nhánh `HỎNG`/`ĐẠT` của cron, ufw, daemon.json, logrotate, timezone chỉ được kiểm bằng sự kiện giả.
- Phép 7 chỉ đọc `ufw status`. Docker publish cổng bằng iptables và bỏ qua `ufw`, nên `ĐẠT` của ufw tự nó không chứng minh cổng kín. Đã đối chiếu `docker-compose.yml`: Postgres (5432), NATS và Grafana (3000) đều bind `127.0.0.1`, nên hiện không lộ ra ngoài; công cụ chưa tự kiểm phần `ports:` này (ngoài phạm vi brief).
- Phép 1 đọc **môi trường**, nên chạy tay ngoài `sched.sh` sẽ báo `HỎNG` nếu `.env` chưa nạp vào shell (đúng theo brief; đã ghi trong thông điệp).
- Test viết cùng lúc với cài đặt (không thấy lần đỏ ban đầu do thiếu module); độ tin cậy dựa vào hai phá thử ở trên.
- Brief không đảo quyết định có chủ ý nào.

---

## Audit của Claude (30/09/2026, 01:30)

### A.1. Kết luận: ĐẠT. Nguyên tắc cốt lõi của brief được giữ đúng.

Claude tự chạy `scripts/sched.sh host-preflight` (đúng dòng lệnh lịch sẽ gọi) và đếm lại từ log, không tin bảng trong báo cáo:

```
DAT   : 4      BOQUA : 8      HONG  : 0      EXIT=0
Luu y: 8 phep kiem BO QUA chua duoc xac nhan — khong tinh la DAT.
```

Tám phép không kiểm được trên Windows đều ra **BỎ QUA kèm lý do cụ thể**, không phép nào ra ĐẠT. Dòng tổng kết tự nói ra rằng 8 phép chưa được xác nhận. Đây đúng là thứ brief đòi, và là điều dự án này từng thiếu ([[golive-gate-den-xanh-gia]]).

### A.2. Kiểm độc lập

- **Cổng bind:** cả bốn dòng `ports:` trong `docker-compose.yml` đều là `127.0.0.1:` (5432, 4222, 4223, 3000) — không cổng nào mở ra ngoài.
- **Giới hạn log:** `docker compose --profile test config` có `max-size` ở đủ 6 service (7 lần xuất hiện, gồm neo `x-logging`).
- **Chạy qua `sched.sh`:** EXIT=0, có dòng log mới đúng mốc thời gian.

### A.3. Agent tự nêu một điểm đúng và quan trọng — Claude xác nhận

Mục 7 của báo cáo: **`ufw` không chi phối cổng do Docker publish** (Docker chèn luật iptables riêng), nên một kết quả `ĐẠT` của phép kiểm ufw **tự nó không chứng minh cổng kín**. Agent đã đối chiếu `docker-compose.yml` và ghi rõ giới hạn này thay vì im lặng.

**Đây là chỗ công cụ vẫn có thể tạo đèn xanh giả trên VPS:** nếu sau này ai đó đổi một dòng `ports:` thành `0.0.0.0:5432:5432`, ufw vẫn `ĐẠT` mà Postgres thì lộ ra internet. Phép kiểm thật sự cần là đọc chính `ports:` của compose. **Giao đợt sau** — Claude không sửa vội lúc 01:30, và hiện **không có rủi ro thực tế** vì cả bốn cổng đang bind `127.0.0.1`.

### A.4. Ghi nhận

- 1.520 test (1.476 + 44). Hai phá thử của agent đúng kiểu: bỏ nhánh HỎNG → 1 test đỏ; cho BỎ QUA tính là ĐẠT → **12** test đỏ, gồm cả các test chống báo đẹp.
- Agent thành thật rằng test viết cùng lúc với cài đặt nên không thấy lần đỏ đầu tiên; độ tin cậy dựa vào hai phá thử. Chấp nhận.
- Chưa chạy trên Linux thật: các nhánh ĐẠT/HỎNG của cron, ufw, daemon.json, logrotate, timezone mới chỉ kiểm bằng sự kiện giả. Lần chạy thật đầu tiên sẽ là ngay sau khi chuyển lên VPS — đúng chỗ công cụ này sinh ra để phục vụ.
- **Giới hạn log chỉ có hiệu lực sau khi container được TẠO LẠI.** Claude chưa tạo lại; sẽ làm cùng lần gộp chunk thứ Bảy.
- Còn lại của chủ dự án: tạo task `trading-host-preflight` (Chủ nhật 07:00) — sẽ là task thứ 15.

