# Báo cáo đợt 132 — quả bom đĩa và không ai canh dung lượng

Base `a1d41b5`. Không commit, không push, không chạm container / `data/orderbook/` / scheduled task.

## 1. Việc 1 — `scripts/disk_check.py`

| Test (`tests/test_disk_check.py`) | Điều kiện |
|---|---|
| `test_khong_dieu_kien_nao_cham_thi_im` | không cái nào |
| `test_duoi_nguong_tuyet_doi_nhung_tren_ty_le` | chỉ ngưỡng 10 GB |
| `test_duoi_ty_le_nhung_tren_nguong_tuyet_doi` | chỉ ngưỡng 10% |
| `test_ca_hai_dieu_kien_cham_...` | cả hai (một cảnh báo) |
| `test_dung_o_nguong_thi_chua_keu` | biên |
| `test_main_gui_hong_tra_2`, `..._nem_ngoai_le_...` | gửi hỏng / ném → 2 |
| `test_main_gui_thanh_cong_tra_1`, `dry_run`, `du_cho_tra_0` | 1 / 1 không gửi / 0 |
| `test_main_duong_dan_khong_ton_tai_tra_2`, `backup_dir_khong_ton_tai` | cấu hình → 2 |
| `test_backup_dir_do_rieng_...` | đo riêng phân vùng sao lưu |
| `test_bao_cao_liet_ke_...` | báo cáo có orderbook/logs |

**Phá thử:** đổi `if free_pct < min_free_pct` → `if False`: đỏ `test_duoi_ty_le_nhung_tren_nguong_tuyet_doi`. Đổi `if free_gb < min_free_gb` → `if False`: đỏ `test_duoi_nguong_tuyet_doi_nhung_tren_ty_le`. Đã khôi phục; 14 passed.

**Chạy thật `--dry-run`** (máy này còn trống 186,1 GB / 449,2 GB = 41,4%): im lặng, `EXIT=0`. Để thấy báo cáo, ép `--min-free-gb 100000`:

```
[CRITICAL] Đĩa sắp đầy (repo: .): còn 186.1 GB (41.4%) — dưới 100000.0 GB
Chiếm chỗ:
  data/orderbook: 25.1 MB
  logs: 0.6 MB
Docker:
  TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
  Images          17        5         3.211GB   141.5MB (4%)
  Containers      6         6         10.15MB   0B (0%)
  Local Volumes   3         3         1.812GB   0B (0%)
  Build Cache     118       0         826.8MB   375.9MB
[DRY-RUN] Không gửi Telegram thật.
EXIT=1
```

Họ mã thoát: họ thứ hai (gửi hỏng → 2). **Không** tái dùng `alert_and_fail` vì nó luôn trả 1 (họ thứ nhất, có test ghim); không sửa helper.

## 2. Việc 2 — `scripts/backup_orderbook.sh` (thử trên bản sao ở thư mục tạm)

- Tar cũ toàn thư mục: **15.540.636 byte**. Lần chạy đầu (bootstrap, chưa có bản nào): 3 file, 15.540.545 byte.
- Thêm một phiên giả (12 MB) rồi chạy: bản mới **12.003.960 byte**, `tar -tzf` chỉ có `data/orderbook/41I1GA000/2026-09-30.jsonl.gz` (một phiên).
- Chạy lần ba liền sau: "nothing to back up", rc=0, không thêm file.
- Thư mục nguồn không có file: không tạo file, rc=0.
- Phá thử (shim `tar` tạo archive rỗng): "verification failed ... Removing it", rc=1, file rác bị xoá.
- Thành viên archive là `data/orderbook/...` nên lệnh khôi phục ở §11 Bước 5 dùng nguyên.

## 3. Việc 3 — dọn rác Docker (chỉ lệnh đọc)

`docker system df` và dangling: xem khối §1 ở trên (Images 17, Build Cache 118/826,8 MB) và:

```
<untagged> 7fef8868bc2f / 681fede19cf6 / f57d9de184aa / 214acb385930  (217MB)
<untagged> dc9b0b7df3d6 / 3b0d943eff62                                (228MB)
```

`docker image inspect ai_auto_trading_system-collector:previous` thành công (`sha256:ed10d45460d6...`, rc=0); `engine:previous` = `5417825676f1`. Cả hai ID **không** nằm trong sáu ID dangling. `docker image prune --help` không có `--dry-run` (Docker 29.8.0) → không kiểm bằng dry-run, chỉ đối chiếu danh sách. Không chạy prune thật.

## 4. Việc 4 — nối lịch

`sched.sh`: thêm `orderbook-backup`, `disk-check`; dòng `dung:` in đủ **14** job. `DEPLOYMENT.md`: §6 bỏ dòng tar cũ, §7 thêm mô hình dung lượng (**tối thiểu ~40 GB, khuyến nghị 60–80 GB**) và mục dọn rác Docker, §9 thêm job 12–13 và hai dòng bảng Windows. `tests/test_deployment_doc.py` xanh.

## 5. Scheduled task Windows đề xuất (chủ dự án tạo)

- `trading-orderbook-backup` — 02:30 hàng ngày, tham số `orderbook-backup`.
- `trading-disk-check` — mỗi 6 giờ, 24/7, tham số `disk-check`.

## 6. Việc 5

Bảng hai họ mã thoát đã ghi vào docstring `scripts/_alert_common.py`; `git diff` chỉ thêm 13 dòng docstring, 0 dòng xoá. `test_alert_common.py` + `test_deploy_drift_check.py` xanh, không sửa dòng nào.

## 7. Kiểm chứng chung

`uv run pytest -q` → **1474 passed** (nats-test chạy). `ruff check trading tests scripts` sạch. `bash -n` sạch. `git ls-files -s`: `sched.sh` 100755; `backup_orderbook.sh` 100755 (đã `git add --intent-to-add --chmod=+x`, chưa commit). `detect_changes`: risk low, 0 process ảnh hưởng (2 symbol "touched" của `_alert_common.py` chỉ do docstring dịch dòng).

## 8. Không kiểm được / brief mơ hồ

- Không kiểm trên Linux/VPS thật; `backup_orderbook.sh` chạy trên Git Bash. Telegram thật không gửi.
- Mặc định `--backup-dir /var/backups/trading-db` không tồn tại trên máy Windows này → `sched.sh disk-check` sẽ trả 2 ở đó (giống `backup-check`); truyền đường dẫn thật khi tạo task Windows.
- **Ruling:** brief nói "chỉ các file của phiên gần nhất *hoặc* chưa từng sao lưu". Chọn "chưa từng sao lưu" (mới hơn bản tar mới nhất); lần chạy đầu tiên không có bản nào thì đóng gói tất cả một lần (bằng đúng bản cũ, 15,5 MB). Nếu chỉ lấy "phiên gần nhất" thì một đêm lỡ job sẽ mất dữ liệu vĩnh viễn. Cổng "chỉ một phiên" được chứng minh ở lần chạy thứ hai.
- Trùng ngày (chạy hai lần có file mới) → thêm hậu tố `_HHMMSS` để không ghi đè.
- Hạn xoá 14 ngày ⇒ kho sao lưu sổ lệnh chỉ giữ ~14 ngày; bản gốc là `data/orderbook/`.
- Con số "10 job"/"9 cron job" cũ trong DEPLOYMENT.md đã lệch; chỉ sửa các chỗ này thành 14 vì liên quan trực tiếp.
- Brief không đảo quyết định có chủ ý nào.
- Review cuối: tự rà (không có reviewer độc lập).

---

## Audit của Claude (29/09/2026, 22:55)

### A.1. Kết luận

Năm việc **ĐẠT** về nội dung; quả bom đĩa đã được gỡ đúng. Nhưng Claude chạy **đúng như lịch sẽ gọi** (không truyền tham số) và cả ba job mới đều hỏng, trong đó một job **gửi cảnh báo giả mỗi ngày**. Claude đã sửa gốc.

Quyết định của agent ở việc 2 **tốt hơn brief của Claude**: brief cho hai lựa chọn, agent chọn "các file **chưa từng được sao lưu**" thay vì "phiên gần nhất", lập luận rằng một đêm lỡ job sẽ mất dữ liệu vĩnh viễn. Đúng. Ghi nhận.

### A.2. Ba job mới hỏng khi gọi đúng như lịch — và một job kêu oan mỗi ngày

`sched.sh` bịa mặc định `/var/backups/trading-db` cho bốn job. Claude chạy không tham số:

```
disk-check       -> EXIT=2   LỖI CẤU HÌNH: --backup-dir không phải thư mục:
                             C:\Program Files\Git\var\backups\trading-db
backup-check     -> EXIT=1   [CRITICAL] Thư mục sao lưu không tồn tại:
                             C:\Program Files\Git\var\backups\trading-db
orderbook-backup -> EXIT=1   mkdir: cannot create directory '/var': Permission denied
```

Hai nguyên nhân chồng lên nhau:
1. **Mặc định chỉ đúng cho Ubuntu.** Trên Windows thư mục đó không tồn tại.
2. **Git Bash dịch đường dẫn.** `/var/backups/trading-db` truyền cho `uv` (một chương trình Windows) bị đổi thành `C:\Program Files\Git\var\...`. Cùng loại bẫy mà `backup_db.sh` đã phải dùng `MSYS_NO_PATHCONV=1` để tránh.

**Hậu quả nặng nhất là `backup-check`**, và nó **đã có từ đợt 131** — Claude audit đợt đó và **không bắt được**, vì chỉ chạy với tham số. Nếu chủ dự án tạo scheduled task theo đúng bảng Claude đưa ở audit 131 mà quên tham số, hệ thống sẽ gửi Telegram *"Thư mục sao lưu không tồn tại"* **mỗi ngày lúc 03:00**, với một đường dẫn bịa. Chuông kêu oan hằng ngày là cách nhanh nhất để người ta thôi tin chuông — đúng họ với [[golive-gate-den-xanh-gia]].

**Bài học cho chính Claude:** audit một job đã lên lịch thì phải chạy **đúng dòng lệnh mà lịch sẽ chạy**, không phải dòng thuận tiện nhất.

### A.3. Claude sửa gốc

Thứ tự tìm thư mục sao lưu, áp cho **cả bốn** job: **tham số** → **`TRADING_BACKUP_DIR` trong `.env`** → mặc định Ubuntu.

- `sched.sh`: **bỏ hẳn** việc bịa mặc định; truyền `"$@"` thẳng xuống. Lý do ghi tại chỗ: `sched.sh` chạy **trước** khi `run_if_docker_up.sh` nạp `.env`, nên ở đó không thể thấy biến — suy mặc định ở đó là sai chỗ. Tham số vị trí vẫn được đổi thành `--backup-dir` cho hai job Python.
- `backup_db.sh`, `backup_orderbook.sh`: `${1:-${TRADING_BACKUP_DIR:-/var/backups/trading-db}}`.
- `backup_check.py`, `disk_check.py`: `DEFAULT_BACKUP_DIR` đọc `TRADING_BACKUP_DIR`.
- `.env.example`: thêm biến kèm cảnh báo dành cho Windows.
- `DEPLOYMENT.md` §6: thêm mục `TRADING_BACKUP_DIR` với bảng ba hậu quả đo được ở trên.

**`disk_check.py` còn một lỗi riêng:** thư mục sao lưu vắng thì nó thoát 2, tức **phép đo phụ hỏng làm chết phép đo chính**. Job này sinh ra để canh đĩa; "có bản sao lưu hay không" đã là việc của `backup_check.py`. Claude đổi thành: ghi chú rồi đo tiếp. Test cũ `test_main_backup_dir_khong_ton_tai_tra_2` ghim hành vi cũ nên Claude **viết lại** nó theo ý định mới (`test_backup_dir_vang_KHONG_duoc_giet_phep_kiem_dia`), chứ không xoá.

**Kiểm lại sau khi sửa** (gọi đúng như lịch):

```
A. khong tham so:   disk-check EXIT=0 (co ghi chu bo qua phep do phu)
B. co tham so:      disk-check EXIT=0, backup-check EXIT=0 (im, ban sao luu con moi)
                    orderbook-backup -> tao archive 3 file, 15 MB, EXIT=0
C. qua TRADING_BACKUP_DIR (khong tham so):
                    backup_check EXIT=0, disk_check EXIT=0, backup_orderbook tao archive
   doi chung: bo bien di -> quay ve /var/backups/trading-db
```

### A.4. Lỗi hình thức: hai case mới mất dấu gạch nối xuống dòng

Hai case `orderbook-backup` và `disk-check` bị dồn thành một dòng dài với khoảng trắng thay cho `\` + xuống dòng, khác khuôn của 12 case còn lại. Chạy vẫn đúng, nhưng Claude đã viết lại cho đồng nhất trong lúc sửa A.3.

### A.5. Kiểm khác

- **Quả bom đã gỡ, đo thật:** lần chạy đầu (bootstrap) 15.540.545 byte = đúng bằng bản tar cũ; lần sau thêm một phiên giả 12 MB thì bản mới chỉ **12.003.960 byte** và `tar -tzf` chỉ có một file phiên đó. Chạy lại ngay: "nothing to back up". Tăng **tuyến tính**, đúng mục tiêu.
- **Việc 3 đúng và cẩn thận:** agent chỉ chạy lệnh đọc, và chứng minh `collector:previous` + `engine:previous` **không** nằm trong sáu image mồ côi — tức `docker image prune -f` sẽ không xoá đường lui. `--dry-run` không có trên Docker 29.8.0 nên agent nói rõ là không kiểm được, thay vì bịa.
- **Việc 5 đúng phạm vi:** `git diff scripts/_alert_common.py` chỉ thêm 13 dòng docstring, 0 dòng xoá; hai file test kia không bị chạm.
- `ruff` sạch; **1.474 passed**; `test_deployment_doc.py` xanh; `bash -n` sạch; `sched.sh` và `backup_orderbook.sh` đều `100755`.
- `_backups/db` không bị đụng trong mọi phép thử của Claude (chỉ ghi vào thư mục tạm).

### A.6. Việc của chủ dự án

Ngoài ba task đã nêu ở audit đợt 131, thêm hai task nữa — và **một việc quan trọng trước tất cả**:

**Đặt `TRADING_BACKUP_DIR=D:/My_Vault_Obsidian/Project/_backups/db` trong `.env`.** Không có nó, ba job trên hỏng đúng như bảng ở §A.2. (Claude không tự sửa `.env` vì đó là file bí mật của chủ dự án.)

| Task | Lịch | Tham số |
|---|---|---|
| `trading-orderbook-backup` | 02:30 hằng ngày | `orderbook-backup` |
| `trading-disk-check` | mỗi 6 giờ, 24/7 | `disk-check` |

Đặt biến rồi thì **không cần** truyền đường dẫn cho task nào nữa.

