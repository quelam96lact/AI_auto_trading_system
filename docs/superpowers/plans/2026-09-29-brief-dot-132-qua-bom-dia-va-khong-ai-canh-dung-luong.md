# Brief đợt 132 — sao lưu sổ lệnh phình theo bình phương, và không ai canh dung lượng đĩa

**Base commit:** `a1d41b5`.
**Người thực thi:** agent — **trọn bộ việc 1–5**, gồm cả nối vào lịch chạy. **Claude:** audit, commit, push.

---

## §0. Bối cảnh — số đo của Claude, 29/09 lúc 22:30

Hệ thống sắp chạy **24/7** trên VPS. Hết đĩa là kiểu chết âm thầm kinh điển của máy chủ chạy liên tục: Postgres ngừng nhận ghi, collector chết, và **bản sao lưu cũng hỏng** — tất cả cùng lúc. Claude kiểm:

**Không có một dòng code nào canh dung lượng đĩa.** Grep toàn repo `disk|df -h|statvfs|shutil.disk`: chỉ có một test giả lập lỗi "Disk full" của bộ ghi sổ lệnh. Không job nào, không cảnh báo nào.

### Quả bom: `DEPLOYMENT.md:174`

```
30 2 * * * tar -czf /var/backups/trading-db/orderbook_$(date +\%Y\%m\%d).tar.gz -C /opt/trading data/orderbook
```

Mỗi đêm nó nén **toàn bộ** `data/orderbook` thành một file mới, và **không có gì xoá file cũ**. Nghĩa là bản ngày N chứa lại tất cả dữ liệu từ ngày 1. Tổng dung lượng tăng theo **bình phương** số phiên.

Số đo thật của Claude:
- `data/orderbook/<mã HĐ>/<ngày>.jsonl.gz`, hiện 3 file, **25 MB**; tốc độ ~**10–15 MB mỗi phiên** (25/09: 9,9 MB; 28/09: 15,0 MB).
- Hệ số nén thật khi `tar -czf` lên các file **đã là `.gz`**: `26.325.734 → 15.540.634 byte`, tức **0,59** — nén thêm được rất ít, đúng như dự đoán với dữ liệu đã nén.

Mô hình với 12 MB/phiên và hệ số 0,59 đã đo:

| Số phiên | `data/orderbook` | **Tổng các file tar** |
|---|---|---|
| 20 (~1 tháng) | 0,2 GB | **1,5 GB** |
| 60 (~3 tháng) | 0,7 GB | **12,7 GB** |
| 125 (~6 tháng) | 1,5 GB | **54 GB** |
| 250 (~1 năm) | 2,9 GB | **217 GB** |

Cộng thêm: sao lưu DB 100 MB/ngày × 14 ngày ≈ 1,4 GB, DB 1 GB và đang tăng, Docker 3,2 GB image + 1,8 GB volume + 0,8 GB build cache. **Một VPS 40–80 GB sẽ đầy trong khoảng 3–6 tháng**, và triệu chứng đầu tiên là DB ngừng ghi.

### Rác Docker tích dần

`docker system df` trên máy này: **6 image mồ côi (dangling)**, **118 mục build cache (827 MB, 376 MB thu hồi được)**. Mỗi lần triển khai theo §10 lại build image mới, nên trên VPS con số này chỉ tăng.

---

## §1. Việc 1 — `scripts/disk_check.py`: cảnh báo trước khi đĩa đầy

Cảnh báo Telegram khi dung lượng trống xuống thấp. **Cảnh báo phải đến sớm hơn lúc hỏng**, nên dùng hai điều kiện, kêu khi **một trong hai** chạm:
- còn trống **dưới một ngưỡng tuyệt đối** (mặc định 10 GB), và
- còn trống **dưới một tỷ lệ** (mặc định 10%).

Lý do cần cả hai: đĩa 500 GB thì 10% là 50 GB (quá sớm), đĩa 40 GB thì 10 GB là 25% (hợp lý). Ghi lý do này vào chú thích.

**Báo cáo kèm theo khi kêu:** liệt kê dung lượng của `data/orderbook`, thư mục sao lưu, `logs/`, và volume Docker — để người đọc biết **cái gì** đang chiếm chỗ, không chỉ biết "sắp đầy".

**Quy ước, theo code sẵn có:**
- Dùng `shutil.disk_usage`. Kiểm đường dẫn nào là tham số `--path` (mặc định thư mục repo); thêm `--backup-dir` để đo luôn nơi chứa sao lưu (trên VPS nó có thể nằm trên phân vùng khác — **phải đo riêng**, đừng giả định cùng ổ).
- Gửi bằng `trading.telegram.send_telegram`, in bằng `trading.alerts._print_safe`, giống `backup_check.py`.
- **Mã thoát:** 0 ổn; 1 có cảnh báo và đã gửi; 2 sai cấu hình **hoặc cảnh báo cần gửi mà gửi hỏng**.
- **Không bao giờ ném ngoại lệ ra ngoài** (FEE-ALARM-2).
- Cờ `--dry-run` in thay vì gửi. Hàm quyết định **thuần**, tách khỏi phần đọc đĩa, để test không cần ổ thật.

**Cổng:** test cho từng điều kiện (dưới ngưỡng tuyệt đối; dưới tỷ lệ; cả hai; không cái nào), test gửi hỏng → mã 2, test đường dẫn không tồn tại. Phá thử: bỏ điều kiện tỷ lệ → test tương ứng đỏ; bỏ điều kiện tuyệt đối → test tương ứng đỏ. Chạy thật `--dry-run` trên máy này, dán nguyên văn.

## §2. Việc 2 — gỡ bom: sao lưu sổ lệnh phải TĂNG TUYẾN TÍNH

`data/orderbook/<mã>/<ngày>.jsonl.gz`: mỗi phiên ghi **một file mới**, và **không sửa file cũ**. Vậy không có lý do gì phải nén lại toàn bộ thư mục mỗi đêm.

**Việc:** `scripts/backup_orderbook.sh` chỉ đóng gói **các file của phiên gần nhất** (hoặc các file chưa từng được sao lưu), thành `orderbook_<ngày>.tar.gz`. Kèm **hạn xoá** như `backup_db.sh` (`BACKUP_RETENTION_DAYS`, mặc định 14).

- **Tự kiểm sau khi tạo:** `tar -tzf` đọc được và số file bên trong **> 0**. Không đạt thì **xoá file rác** và thoát khác 0 — một file rỗng mang tên hợp lệ sẽ làm `backup_check` tưởng có bản sao lưu.
- Nếu phiên gần nhất **không có file nào** (ngày nghỉ, hoặc bộ ghi không chạy): **không tạo file rỗng**, in rõ lý do, thoát 0. Ngày nghỉ không phải lỗi.
- Giữ `set -euo pipefail`, tham số thư mục đích thứ nhất, và khuôn chú thích của `backup_db.sh`.
- **Bỏ dòng cron tar cũ** ở `DEPLOYMENT.md:174` và thay bằng job mới (việc 4).

**Cổng:**
- Chạy thật ra thư mục tạm: file tạo ra chỉ chứa **các file của một phiên**, không chứa toàn bộ thư mục. Dán `tar -tzf` để chứng minh.
- **So dung lượng:** kích thước bản mới so với bản `tar` toàn thư mục hiện tại (14 MB). Dán cả hai con số.
- Chạy **hai lần liên tiếp**: lần hai không được nhân đôi dữ liệu.
- Ngày không có dữ liệu → không tạo file, thoát 0.
- Phá thử: tạo file tar rỗng rồi chạy bước tự kiểm → phải bị bắt và xoá.

## §3. Việc 3 — dọn rác Docker, nhưng KHÔNG được xoá đường lui

**Bẫy chết người:** `docker image prune -a` xoá **mọi** image không có container đang dùng — **kể cả `:previous`**, tức xoá mất đường rollback của §10. **Cấm dùng `-a`.**

**Việc:** thêm bước dọn rác **an toàn** vào `DEPLOYMENT.md` (chỉ tài liệu, §7 hoặc §10 — chọn một chỗ, nêu lý do):
- `docker image prune -f` (chỉ image **dangling**, không đụng tag nào), và
- `docker builder prune -f --filter until=168h` (build cache cũ hơn 7 ngày).

**Cổng (chỉ lệnh ĐỌC trên máy này, KHÔNG chạy prune thật):**
- `docker image ls --filter dangling=true` và `docker system df` trước — dán nguyên văn.
- Chứng minh `:previous` **không** nằm trong tập dangling: `docker image inspect ai_auto_trading_system-collector:previous` thành công, và nó không xuất hiện trong danh sách dangling.
- Dùng `docker image prune --dry-run` nếu bản Docker hỗ trợ; nếu không hỗ trợ thì **nói rõ là không kiểm được** và chỉ đối chiếu danh sách. **Không** chạy prune thật.

## §4. Việc 4 — nối vào lịch và ghi mô hình dung lượng

- `scripts/sched.sh`: thêm case `disk-check` và `orderbook-backup`, qua `run_if_docker_up.sh`, đúng khuôn các case sẵn có. Cập nhật khối chú thích đầu file và dòng `dung:` (sẽ thành **14** job).
- `DEPLOYMENT.md` §9: thêm hai dòng cron. `orderbook-backup` **02:30 hằng ngày** (thay dòng tar cũ ở §6). `disk-check` đề xuất **mỗi 6 giờ, 24/7** — nêu lý do trong chú thích. **Xoá dòng tar cũ ở §6**, thay bằng câu trỏ sang §9 (đừng để hai bản, xem bài học ở `README_VPS_UBUNTU.md` đợt 131).
- **Ghi mô hình dung lượng vào `DEPLOYMENT.md`** (§7): bảng ở §0 của brief này, kèm câu "VPS cần tối thiểu bao nhiêu GB" suy ra từ hạn xoá 14 ngày. Đây là con số chủ dự án cần để chọn gói VPS.

**Cổng:** `uv run pytest tests/test_deployment_doc.py` xanh (nó buộc tập job hai bên bằng nhau). `bash -n` sạch. Gọi `sched.sh` với job sai phải in đủ **14** job.

## §4b. Việc 5 — ghi rõ HAI họ mã thoát, để không ai gộp nhầm

Claude tự soát và thấy repo đang có **hai** hợp đồng mã thoát khác nhau cho các job cảnh báo. Cả hai đều đúng, nhưng chỗ khác nhau **không được ghi ở đâu cả**, nên script thứ tư rất dễ chọn nhầm.

| Họ | Ai dùng | `1` nghĩa là | Khi gửi Telegram hỏng |
|---|---|---|---|
| **Theo phát hiện** | `deploy_drift_check.py`, `check_silent_engine.py` (qua `_alert_common.alert_and_fail`) | *có vấn đề được phát hiện* | vẫn trả **1** |
| **Theo gửi được hay không** (đợt 126) | `docker_down_alert.py`, `container_health_check.py`, `backup_check.py` | *đã gửi thành công* | trả **2** |

**CẤM đổi `alert_and_fail` để nó trả 2.** `tests/test_deploy_drift_check.py:86` khẳng định `rc == 1` kèm chú thích *"gui hong van phai bao lech"* — đó là **quyết định có chủ ý, đã có test ghim**. Với `deploy-drift`, `1` mã hoá *"có lệch triển khai"*, không phải *"đã gửi xong"*.

**Việc:**
- `disk_check.py` (việc 1) thuộc họ **thứ hai** (như `backup_check.py`): gửi hỏng → **2**. Nếu tái dùng được `_alert_common.alert_and_fail` mà vẫn giữ đúng hợp đồng này thì tái dùng; **không** thì nói rõ vì sao trong báo cáo, và **không** sửa helper.
- Bổ sung vào docstring của `scripts/_alert_common.py` một đoạn ngắn nêu đúng bảng trên, kèm câu: *"Trước khi gộp hai họ này làm một, đọc `test_deploy_drift_check.py:86`."* Đây là việc **chỉ thêm chú thích**, không đổi một dòng code nào của helper.

**Cổng:** `tests/test_alert_common.py` và `tests/test_deploy_drift_check.py` phải **xanh y nguyên**, không sửa một dòng nào trong hai file đó. `git diff scripts/_alert_common.py` chỉ được chạm docstring.

## §5. Tiêu chí chung

```
uv run pytest -q   (TOÀN BỘ, nats-test chạy)   → ≥ 1.460 passed + test mới, 0 failed
uv run ruff check trading tests scripts        → sạch
uv run pytest tests/test_deployment_doc.py      → xanh
bash -n cho mọi *.sh đã sửa                     → sạch
git ls-files -s cho mọi *.sh đã sửa/tạo         → 100755
```

`npx gitnexus detect-changes --repo AI_auto_trading_system` ở cuối.

## §6. Phạm vi

**Được sửa/tạo:** `scripts/disk_check.py`, `scripts/backup_orderbook.sh`, `tests/test_disk_check.py` (mới); `scripts/_alert_common.py` (**chỉ docstring**, việc 5); `scripts/sched.sh` (**chỉ** thêm hai case + chú thích + dòng `dung:`); `DEPLOYMENT.md` (§6 xoá dòng tar cũ, §7 mô hình dung lượng + dọn rác Docker, §9 hai dòng cron); báo cáo `docs/superpowers/research/2026-09-29-dot-132-qua-bom-dia.md`.

**KHÔNG được đụng:** `trading/`; `scripts/backup_db.sh`, `scripts/backup_check.py`, `scripts/container_health_check.py` (vừa xong đợt 131); **phần code** của `scripts/_alert_common.py`, và `tests/test_alert_common.py`, `tests/test_deploy_drift_check.py`, `scripts/deploy_drift_check.py`, `scripts/check_silent_engine.py` (xem việc 5); `docker-compose.yml`; `.githooks/`; các case sẵn có trong `sched.sh`; test của đợt khác; **`data/orderbook/` — không xoá, không sửa, không di chuyển file nào** (đây là dữ liệu nghiên cứu, chỉ được ĐỌC); mọi container đang chạy.

## §7. Điều cấm

- **Không commit, không push.** Không rebuild, không restart container.
- **Không chạy `docker image prune`, `docker builder prune`, `docker system prune` thật** — chỉ lệnh đọc (xem §3).
- **Không xoá bất kỳ file nào trong `data/orderbook/` hay `_backups/`.** Phép thử ghi vào thư mục tạm.
- Không gửi Telegram thật: `--dry-run` hoặc hàm gửi giả.
- Không đọc `.env` thật; không kết nối SSI; không đặt lệnh; không `--send`.
- Cấm `git checkout`, `git restore`, `git stash` (trừ `git stash create`).
- Không tạo, sửa, xoá scheduled task — ghi tên job và lịch đề xuất vào báo cáo để chủ dự án tạo.
- **Không chạy `merge_bars_daily_chunks.py` với DSN của DB `trading`**: việc đó của Claude thứ Bảy.

## §8. Báo cáo phải có

1. Việc 1: bảng test ↔ điều kiện, phá thử, và lần chạy thật `--dry-run` **nguyên văn** (gồm cả dung lượng trống thực tế của máy này).
2. Việc 2: `tar -tzf` của bản mới (chứng minh chỉ một phiên), **hai con số dung lượng** để so, kết quả chạy hai lần, và trường hợp ngày không có dữ liệu.
3. Việc 3: đầu ra `docker system df` và danh sách dangling **nguyên văn**, cộng bằng chứng `:previous` không nằm trong đó.
4. Việc 4: diff, `test_deployment_doc.py` xanh, dòng `dung:` đủ 14 job, và bảng mô hình dung lượng đã ghi vào §7.
5. Tên job và lịch đề xuất cho scheduled task Windows.
6. Việc 5: bảng hai họ mã thoát đã ghi vào docstring, `git diff scripts/_alert_common.py` chứng minh chỉ chạm docstring, và hai file test kia xanh y nguyên.
7. Những gì **không** kiểm được, và vì sao.
8. Chỗ nào brief sai hoặc mơ hồ. **Nếu brief đảo một quyết định có chủ ý nào** (đọc chú thích trước khi sửa), **báo ngay**.
