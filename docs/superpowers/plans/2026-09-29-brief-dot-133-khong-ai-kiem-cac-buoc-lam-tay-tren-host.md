# Brief đợt 133 — `DEPLOYMENT.md` có hàng chục bước làm tay, và không gì kiểm chúng đã được làm

**Base commit:** `c5934d1`.
**Người thực thi:** agent — **trọn bộ việc 1–3**, gồm cả nối vào lịch. **Claude:** audit, commit, push.

---

## §0. Bối cảnh — số đo của Claude, 29/09 lúc 23:15

Việc chuyển lên VPS **làm đúng một lần**. `DEPLOYMENT.md` yêu cầu hàng chục bước **làm tay** trên host, và Claude vừa kiểm: **không có gì kiểm lại chúng.**

`scripts/check_golive_gate.py` có 9 tiêu chí, nhưng tất cả đều là **trạng thái ứng dụng**: NAV, sức mua, độ tươi vị thế, lệch triển khai, Telegram, độ phủ nến, cờ `real_trading_enabled`. Grep `crontab|daemon.json|timedatectl|ufw|logrotate|600|TRADING_BACKUP` trong file đó: **0 kết quả**.

Nghĩa là mọi bước sau đây, nếu quên, sẽ **im lặng**:

| Bước làm tay | Ở đâu | Quên thì sao |
|---|---|---|
| `TRADING_BACKUP_DIR` trong `.env` | §6 (đợt 132) | `backup-check` kêu oan mỗi ngày, `disk-check` không kiểm đĩa, `orderbook-backup` chết — **đã đo thật 29/09** |
| Cài khối cron §9 (14 job) kèm `CRON_TZ` | §9 | job không chạy; không cảnh báo nào vì chính cảnh báo cũng là cron |
| `/etc/docker/daemon.json` giới hạn log | §8 | log container tăng không giới hạn |
| `/etc/logrotate.d/trading` | §8 | log trên host tăng không giới hạn |
| `chmod 600 .env` | §11 Bước 5 | bí mật đọc được bởi user khác |
| `sed -i 's/\r$//' .env` | §11 Bước 5 | mọi giá trị dính `\r`, kể cả token |
| Múi giờ `Asia/Ho_Chi_Minh` | §1 | mọi mốc giờ phiên sai |
| `ufw` chỉ mở cổng cần | §3 | Postgres/Grafana lộ ra internet |
| Thư mục sao lưu tồn tại và ghi được | §6 | sao lưu hỏng |
| Đĩa đủ lớn (tối thiểu ~40 GB) | §7 (đợt 132) | đầy trong 3–6 tháng |
| Cờ thực thi các script | §2 | cron chết `Permission denied` (đợt 125 đã vấp) |

**Nguyên tắc bắt buộc của đợt này:** công cụ mới **không bao giờ được báo ĐẠT cho thứ nó không kiểm được**. Dự án này đã có một cổng báo đèn xanh giả đúng ngày hệ thống chết cả phiên. Vì vậy **ba trạng thái**: `ĐẠT` / `HỎNG` / `BỎ QUA (kèm lý do)`. Trên Windows thì `ufw`, `systemd`, `logrotate`, `crontab` không có — phải ra `BỎ QUA`, **không** phải `ĐẠT`.

---

## §1. Việc 1 — `scripts/host_preflight.py`

Một lệnh chủ dự án chạy **trên host** ngay sau khi chuyển máy, và chạy lại định kỳ. In một bảng, mỗi dòng là một bước ở §0.

**Thiết kế bắt buộc:**
- Hàm quyết định **thuần**: nhận vào các sự kiện đã đo (dict/dataclass) và trả danh sách kết quả. Phần đọc host (chạy lệnh, đọc file) tách riêng. Test không được cần host thật.
- **Ba trạng thái**, và bảng tổng kết cuối phải đếm riêng từng loại. `BỎ QUA` phải kèm **lý do cụ thể** ("không có `ufw` trên hệ này"), không được để trống.
- **Mã thoát:** `0` khi không có `HỎNG` nào; `1` khi có `HỎNG`; `2` khi sai cấu hình chính công cụ (ví dụ không đọc được repo). `BỎ QUA` **không** làm mã thoát khác 0 — nhưng phải hiện rõ trong bảng.
- **Chỉ ĐỌC.** Không sửa `.env`, không cài cron, không đổi múi giờ, không chạy `ufw`. Nó **báo**, người vận hành sửa.
- **Không in bí mật.** Kiểm `.env` thì chỉ được in *tên* biến và *quyền file*, tuyệt đối không in giá trị. Kiểm CRLF thì đếm, không in nội dung.
- `--json` để xuất máy đọc được (hữu ích khi nối vào job sau).

**Các phép kiểm, mỗi phép nói rõ nó đọc gì:**
1. `TRADING_BACKUP_DIR` có mặt trong môi trường **và** thư mục đó tồn tại, ghi được. *(Đọc biến môi trường, không đọc `.env`.)*
2. `crontab -l` chứa **đủ** tập job của `scripts/sched.sh` (suy tập job từ chính `sched.sh`, **đừng viết cứng 14**), và có dòng `CRON_TZ=Asia/Ho_Chi_Minh`.
3. `/etc/docker/daemon.json` có `log-opts.max-size` và `max-file`. Không có file → `HỎNG`; không đọc được (quyền) → `BỎ QUA` kèm lý do.
4. `/etc/logrotate.d/trading` tồn tại.
5. `.env` mode `600` (Linux), và **0** ký tự `\r`.
6. Múi giờ hệ thống là `Asia/Ho_Chi_Minh`.
7. `ufw status` cho thấy đang bật, và Postgres (5432) / Grafana (3000) **không** mở ra ngoài.
8. Dung lượng đĩa còn trống ≥ ngưỡng, và tổng dung lượng ≥ ~40 GB (§7).
9. Cờ thực thi: mọi `scripts/*.sh` và `.githooks/pre-push` đều thực thi được.
10. `config/config.yaml` có `real_trading_enabled: false`.
11. Đồng hồ hệ thống đồng bộ (`timedatectl` có `System clock synchronized: yes`, hoặc tương đương). Lệch đồng hồ làm mốc nến sai mà không có triệu chứng nào khác.

**Cổng:**
- Test cho **từng** phép kiểm, cả ba trạng thái ở những phép có thể `BỎ QUA`. Dùng sự kiện giả, không cần host thật.
- **Test chống báo đẹp:** một trường hợp mà công cụ **không đo được gì cả** (ví dụ mọi lệnh đều thiếu) phải ra toàn `BỎ QUA` và **mã thoát 0 kèm cảnh báo rõ ràng rằng không kiểm được gì** — đây là chỗ dễ trở thành đèn xanh giả nhất, nên phải có test ghim và phải ghi rõ trong bảng.
- **Phá thử:** cho một phép kiểm luôn trả `ĐẠT` → test tương ứng đỏ. Cho `BỎ QUA` được tính là `ĐẠT` → test chống báo đẹp đỏ. Dán thông điệp đỏ nguyên văn.
- **Chạy thật trên máy này** (Windows): dán **nguyên văn** bảng. Dự kiến nhiều dòng `BỎ QUA` — đó là kết quả đúng, và chính là bằng chứng công cụ không báo đẹp.

## §2. Việc 2 — giới hạn log Docker đặt TRONG repo, không để trong file của máy

`docker-compose.yml` hiện **không có** cấu hình `logging` nào, nên Docker dùng `json-file` không giới hạn. `DEPLOYMENT.md` §8 có cách sửa, nhưng nó là **bước tay** sửa `/etc/docker/daemon.json` — tức có thể quên, và chỉ áp cho máy đó.

Số đo của Claude (ngoài giờ phiên): `collector` ~26 KB/giờ, `postgres` ~5 KB/giờ, ba service còn lại 0 — cỡ 0,25 GB/năm. **Không phải quả bom**, nên đây là việc dọn cho gọn, không phải việc chữa cháy. Đừng phóng đại trong báo cáo.

**Việc:** thêm khối `logging` (`json-file`, `max-size`, `max-file`) cho **mọi** service trong `docker-compose.yml`. Đây là cùng bài học đợt 129: cấu hình nằm trong repo thì không thể quên, và áp cho cả VPS. Cập nhật §8 để nói rõ khối trong repo là lớp chính, còn `daemon.json` là lớp cho các container **không** thuộc compose.

**Cổng:** `docker compose config -q` sạch; `docker compose config` cho thấy `logging` ở cả 6 service. **Không** restart container nào — Claude áp sau. Nêu rõ trong báo cáo rằng giới hạn chỉ có hiệu lực sau khi container được tạo lại.

## §3. Việc 3 — nối vào lịch

- `scripts/sched.sh`: thêm case `host-preflight`, qua `run_if_docker_up.sh`, đúng khuôn các case sẵn có. Cập nhật khối chú thích đầu file và dòng `dung:` (thành **15** job).
- `DEPLOYMENT.md` §9: thêm dòng cron. Đề xuất **mỗi tuần một lần** (không cần dày: cấu hình host ít đổi) — nêu lý do trong chú thích. Và thêm một câu ở §11 (sau Bước 8) bảo chạy `host-preflight` **ngay sau khi chuyển máy**, trước khi coi là xong.
- `test_deployment_doc.py` buộc hai chỗ khớp nên phải xanh.

## §4. Tiêu chí chung

```
uv run pytest -q   (TOÀN BỘ, nats-test chạy)   → ≥ 1.476 passed + test mới, 0 failed
uv run ruff check trading tests scripts        → sạch
uv run pytest tests/test_deployment_doc.py      → xanh
docker compose config -q                        → sạch
bash -n scripts/sched.sh                        → sạch
git ls-files -s scripts/sched.sh                → 100755
```

`npx gitnexus detect-changes --repo AI_auto_trading_system` ở cuối.

## §5. Phạm vi

**Được sửa/tạo:** `scripts/host_preflight.py`, `tests/test_host_preflight.py` (mới); `docker-compose.yml` (**chỉ** thêm khối `logging`); `scripts/sched.sh` (**chỉ** thêm một case + chú thích + dòng `dung:`); `DEPLOYMENT.md` (§8, §9, và một câu ở §11); báo cáo `docs/superpowers/research/2026-09-29-dot-133-host-preflight.md`.

**KHÔNG được đụng:** `trading/`; `scripts/check_golive_gate.py` (cổng go-live là việc khác — **không** gộp vào); các script của đợt 129–132; `.githooks/`; `config/`; các case sẵn có trong `sched.sh`; test của đợt khác; `.env` thật; mọi container đang chạy (**không** `up`/`restart`/`down`).

## §6. Điều cấm

- **Không commit, không push.** Không rebuild, không restart container.
- **Không sửa gì trên host:** không cài cron, không sửa `daemon.json`, không `ufw`, không đổi múi giờ, không `chmod` file thật. Công cụ này **chỉ đọc**.
- **Không đọc giá trị trong `.env` thật**, không in bí mật. Chỉ được kiểm quyền file và đếm ký tự `\r`.
- Không gửi Telegram; không kết nối SSI; không đặt lệnh; không `--send`.
- Cấm `git checkout`, `git restore`, `git stash` (trừ `git stash create`).
- Không tạo, sửa, xoá scheduled task — ghi tên job và lịch đề xuất vào báo cáo.
- **Không chạy `merge_bars_daily_chunks.py` với DSN của DB `trading`.**

## §7. Báo cáo phải có

1. Việc 1: bảng test ↔ phép kiểm (nêu rõ phép nào có test cho cả `BỎ QUA`), phá thử với thông điệp đỏ nguyên văn, và **bảng chạy thật trên máy này nguyên văn**.
2. Nói rõ phép kiểm nào **không** kiểm được trên Windows và vì sao — và chứng minh chúng ra `BỎ QUA`, không phải `ĐẠT`.
3. Việc 2: diff, `docker compose config` cho thấy `logging` ở 6 service, và câu ghi nhận rằng phải tạo lại container mới có hiệu lực.
4. Việc 3: diff, `test_deployment_doc.py` xanh, dòng `dung:` đủ 15 job.
5. Tên job và lịch đề xuất cho scheduled task Windows.
6. Những gì **không** kiểm được, và vì sao.
7. Chỗ nào brief sai hoặc mơ hồ. **Nếu brief đảo một quyết định có chủ ý nào** (đọc chú thích trước khi sửa), **báo ngay**.
