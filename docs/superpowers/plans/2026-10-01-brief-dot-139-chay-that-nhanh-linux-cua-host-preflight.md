# Brief đợt 139 — chạy THẬT các nhánh Linux của `host_preflight`, trước ngày lên VPS

## Vì sao

Hệ thống thật sẽ chạy trên VPS Linux 24/7. `scripts/host_preflight.py` (đợt 133) là công cụ duy nhất
kiểm các bước làm tay trên host. Nhưng trên máy dev Windows, **8 trong 13 phép kiểm ra BỎ QUA**. Nhánh
ĐẠT/HỎNG Linux của chúng mới chỉ được kiểm bằng **dữ kiện giả tiêm vào test**, chưa từng đọc đầu ra thật
của `crontab -l`, chưa từng `stat` một file `.env` thật, chưa từng mở `/etc/docker/daemon.json` thật.

Nếu một bộ phân tích đọc sai định dạng thật thì lỗi sẽ lộ ra đúng ngày lên VPS, dưới dạng **ĐẠT giả**.
Đó là thứ công cụ này sinh ra để diệt ([[golive-gate-den-xanh-gia]]). Đợt 138 vừa cho thấy cách làm
này hiệu quả: một nhánh chỉ được test bằng giả, khi Claude cho chạy trọn đường thật, mới được xác nhận.

Kèm một việc nhỏ agent đợt 135 đã nêu: phép 12 chỉ đọc **cấu hình** compose, không nhìn cổng **đang
nghe thật**. Container chưa được tạo lại theo compose mới, hoặc một Postgres cài thẳng trên host, sẽ
lọt qua phép 12.

## Giới hạn

- **KHÔNG commit, KHÔNG push.** Không tạo scheduled task. Không sửa `.env`.
- **Không đụng các container của dự án**: không restart, không rebuild, không `docker compose down`.
- **Được phép** chạy container **dùng một lần** (`docker run --rm`) từ image công khai
  (`ubuntu:24.04` hoặc `python:3.11-slim`). Không publish cổng (`-p`), không `--privileged`, không
  `--network host`. Container phải tự huỷ khi xong.
- **Không mount repo và không để `.env` thật lọt vào container.** Đưa mã vào bằng
  `git ls-files -z --cached --others --exclude-standard | tar --null -T - -cf - | docker run -i ...`.
  Lệnh này lấy bản đang sửa trong cây làm việc và bỏ qua file bị `.gitignore` (gồm `.env`). Rồi
  **kiểm và dán bằng chứng** rằng không có `.env` nào trong container trước khi tạo `.env` giả.
- Chỉ sửa `scripts/host_preflight.py`, `tests/test_host_preflight.py`, và đúng các dòng liên quan
  trong `DEPLOYMENT.md`. Kịch bản dựng container (nếu có) đặt ở `scripts/` với tên rõ nghĩa; **không**
  thêm vào `sched.sh`.
- GitNexus: `impact` trước khi sửa symbol, `detect_changes` sau khi sửa.

## Việc 1 — chạy thật các nhánh Linux, có đối chứng hai chiều

Trong container Linux, cài đúng những gì phép kiểm cần (`cron`, `logrotate`, `iproute2`, python +
`pyyaml` + `tzdata`).

**Chạy công cụ dưới HAI danh tính — đây là phần quan trọng nhất của đợt.** Claude đã đọc
`DEPLOYMENT.md`:
- Dòng 452 và 995 cài 16 job bằng **`sudo crontab -e`**, tức crontab của **root**. Vậy khi cron gọi
  `host-preflight` thì nó chạy dưới quyền **root**.
- Nhưng mục "Chạy `host-preflight` ngay sau Bước 8" bảo người vận hành gõ
  `cd /opt/trading && scripts/sched.sh host-preflight` **không có `sudo`**, tức dưới tài khoản
  `<ĐIỀN: USER>` (dòng 12). Khi đó `crontab -l` đọc crontab **của tài khoản thường**, là **rỗng**.

Nghi vấn cần đo, không được đoán:
1. Chạy tay như tài liệu dạy → phép crontab ra **HỎNG oan**, vì đọc nhầm crontab.
2. Cron chạy dưới root → `os.access(..., W_OK)` và `X_OK` gần như luôn đúng với root. Phép "thư mục sao
   lưu ghi được" và phép "cờ thực thi" có thể thành **ĐẠT giả**. Dữ kiện của phép cờ thực thi hiện
   dùng `os.access(p, os.X_OK)`: với root, nó đúng khi **bất kỳ** bit `x` nào được bật.

Trong container, tạo người dùng thường `trader`. Đặt crontab cho **root** đúng như tài liệu. Chạy mọi
ca dưới **cả root lẫn `trader`**, và thêm một cột cho mỗi danh tính vào bảng dưới. Mỗi chỗ hai cột
khác nhau là một phát hiện. Đề xuất cách sửa trong báo cáo, và **nêu rõ phương án** trước khi làm:
sửa công cụ (vd đọc `sudo crontab -l -u root`, đo bit mode thay vì `os.access`), sửa tài liệu (vd
`sudo scripts/sched.sh host-preflight`), hay cả hai. Chọn cách mà **lần chạy tay và lần chạy cron cho
cùng một kết quả**, rồi làm. Nếu phương án cần đổi hành vi ngoài `host_preflight.py` và
`DEPLOYMENT.md` thì **dừng lại và báo**.

Với **mỗi** phép kiểm dưới đây, dựng một trạng thái phải ra ĐẠT và một trạng thái phải ra HỎNG, chạy
`host_preflight.py` thật, dán nguyên văn dòng kết quả:

| Phép | Trạng thái ĐẠT | Trạng thái HỎNG |
|---|---|---|
| crontab | crontab có đủ job của `sched.sh` và `CRON_TZ`, chép đúng khối trong `DEPLOYMENT.md` §9 | thiếu một job; và một lần khác thiếu `CRON_TZ` |
| daemon.json | có `max-size` và `max-file` | thiếu file; và một lần khác JSON hỏng |
| logrotate | có `/etc/logrotate.d/trading` | không có |
| `.env` mode 600 | `chmod 600` | `chmod 644` |
| múi giờ | `/etc/timezone` = `Asia/Ho_Chi_Minh` | `Etc/UTC` |
| cờ thực thi | `scripts/*.sh` và `.githooks/pre-push` có `+x` | bỏ `+x` một file |

Hai phép dự kiến **vẫn BỎ QUA** trong container không có systemd: `ufw` và đồng hồ
(`timedatectl`). Ghi rõ lý do thật (dán thông báo lỗi), **đừng** cố làm chúng ĐẠT bằng
`--privileged`.

**Nếu một dòng ra khác kỳ vọng thì đó là phát hiện, không phải thất bại của đợt này.** Dừng lại, ghi
nguyên văn đầu ra thật, tìm nguyên nhân, sửa bộ phân tích, rồi thêm một test dùng **đúng chuỗi đầu ra
thật vừa bắt được** làm dữ kiện. Đó là lý do đợt này tồn tại.

Ghi chú: trong container không có Docker, nên phép 12 sẽ đi **đường đọc file compose**. Dán dòng của
nó; đó cũng là lần đầu đường này chạy trên Linux.

## Việc 2 — phép kiểm 14: cổng ĐANG NGHE thật

1. Chỉ trên Linux: `ss -ltnH`. Không có `ss` hoặc không phải Linux → BỎ QUA kèm lý do.
2. Cổng cần xét: các cổng publish mà phép 12 đọc được. Nếu phép 12 BỎ QUA thì dùng `CLOSED_PORTS`.
3. Có tiến trình nghe trên một cổng đó ở địa chỉ **ngoài loopback** (`0.0.0.0`, `*`, `[::]`, IP thật)
   → HỎNG, nêu cổng và địa chỉ. Chỉ nghe trên `127.0.0.1`/`[::1]` → ĐẠT.
4. **Không có gì nghe** trên các cổng đó → ĐẠT, nhưng chi tiết phải nói thẳng *"không có tiến trình nào
   nghe — container có đang chạy không?"*. Phép này kiểm **lộ cổng**, không kiểm sống/chết (đã có
   `container-health`); nhưng đừng để một chữ ĐẠT trơn trông như "đã kiểm Postgres và nó kín".
5. Phân tích bằng hàm thuần, test với **chuỗi `ss -ltnH` thật** bắt được trong container. Không tự bịa
   định dạng: IPv6 có ngoặc vuông, có dòng `%lo`, có cột thừa.

Đối chứng trong container: `python3 -m http.server 3000 --bind 0.0.0.0 &` → HỎNG; dừng nó, chạy lại
với `--bind 127.0.0.1` → ĐẠT; không chạy gì → ĐẠT kèm câu cảnh báo ở mục 4. Dán cả ba.

## Tiêu chí hoàn thành

1. Bảng sáu phép Việc 1 đủ **12 trạng thái** (6 ĐẠT + 6 HỎNG), cộng hai trạng thái HỎNG phụ
   (thiếu `CRON_TZ`, JSON hỏng), **mỗi trạng thái có kết quả dưới cả root và `trader`**, cộng ba dòng
   Việc 2. Mỗi dòng đi kèm lệnh đã dựng trạng thái đó.
   - Thêm một ca riêng cho phép "thư mục sao lưu ghi được": thư mục thuộc root, mode `755` → dưới
     `trader` phải HỎNG. Dưới root thì dán kết quả thật, rồi giải thích nó có nghĩa gì cho job cron
     (cũng chạy dưới root).
   - Sau khi sửa: chạy lại toàn bộ bảng, hai cột phải **khớp nhau** ở mọi phép có thể khớp. Chỗ nào
     vẫn khác thì giải thích vì sao đó là đúng.
2. Bằng chứng không có `.env` thật trong container: `ls -la` thư mục gốc repo trong container **trước**
   khi tạo `.env` giả.
3. Mọi phát hiện trong Việc 1 có một test mới dùng chuỗi thật. Nếu không có phát hiện nào thì nói rõ
   "không có"; **đừng** thêm test cho có.
4. Test phép 14 phủ: loopback v4, loopback v6 `[::1]`, `0.0.0.0`, `*`, `[::]`, không có gì nghe, không
   có `ss`. **Phá thử:** coi `[::]` là loopback → phải có test đỏ. Khôi phục, đối chiếu hash.
5. Chạy thật `scripts/sched.sh host-preflight` trên máy dev: kỳ vọng **6 ĐẠT / 0 HỎNG / 9 BỎ QUA** (phép 14
   BỎ QUA vì không phải Linux). Dán bảng.
6. `docker ps -a` sau cùng không còn container dùng một lần nào. Các container dự án có cùng
   `StartedAt` trước và sau đợt này; dán cả hai.
7. `ruff` sạch; `uv run pytest -q` ≥ **1.630 passed** cộng số test mới; `test_deployment_doc.py` xanh.

## Báo cáo

`docs/superpowers/research/2026-10-01-dot-139-nhanh-linux-host-preflight.md`:

- Nguyên văn mọi dòng kết quả thật.
- Brief sai ở đâu thì nói ra.
- Cái gì không kiểm được (ufw, đồng hồ, Docker thật trên Linux) thì ghi rõ là **không kiểm được**. Đó
  vẫn là việc của lần chạy đầu tiên trên VPS.
