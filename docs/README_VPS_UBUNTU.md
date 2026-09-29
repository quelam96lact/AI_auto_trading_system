# README triển khai lên VPS Ubuntu

Tài liệu này là đường đi ngắn để đưa AI Auto Trading System lên một VPS Ubuntu
mới. Hệ thống chạy bằng Docker Compose gồm `collector`, `engine`, PostgreSQL /
TimescaleDB, NATS và Grafana. Mặc định đây là **paper trading**;
`real_trading_enabled` phải giữ `false` cho đến khi hoàn tất quy trình xác nhận
lệnh thật.

Tài liệu chính thức đầy đủ về kiến trúc, token SSI, TLS, backup/restore, log
rotation, và deployment drift nằm tại [DEPLOYMENT.md](../DEPLOYMENT.md). Khi có
thắc mắc về chi tiết chung, **luôn đối chiếu với DEPLOYMENT.md**.

## 1. Điều kiện trước khi bắt đầu

- Ubuntu 22.04 LTS hoặc mới hơn, có quyền `sudo`, kết nối SSH bằng khóa.
- Tối thiểu 2 vCPU, 4 GB RAM và 30 GB SSD; cần tăng tài nguyên theo `docker
  stats` sau vài ngày vận hành.
- Tên miền chỉ cần nếu muốn mở Grafana qua HTTPS. Không mở trực tiếp PostgreSQL,
  NATS hoặc Grafana ra Internet.
- Thông tin SSI FastConnect và (khuyến nghị) bot Telegram để nhận cảnh báo.

Trước khi tiếp tục, hoàn tất checklist còn mở trong
[GO_LIVE_AUDIT.md](../GO_LIVE_AUDIT.md). Việc triển khai hạ tầng không phải là
ủy quyền bật lệnh thật.

## 2. Chuẩn bị VPS

Đăng nhập bằng một người dùng có quyền `sudo`, sau đó cài Docker, Compose, Git,
UFW và `uv` (cần cho các job kiểm tra chạy trên host):

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin git curl ufw
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
sudo install -m 0755 "$HOME/.local/bin/uv" /usr/local/bin/uv
```

Đăng xuất SSH rồi đăng nhập lại sau lệnh `usermod` để quyền nhóm Docker có hiệu
lực. Nhóm `docker` có đặc quyền tương đương root trên máy chủ; chỉ cấp cho
người vận hành tin cậy.

Kiểm tra các công cụ trước khi triển khai:

```bash
docker --version
docker compose version
uv --version
```

Thiết lập firewall. Docker Compose chỉ bind các cổng nội bộ vào `127.0.0.1`,
nhưng firewall vẫn là lớp phòng vệ bắt buộc:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw enable
sudo ufw status verbose
```

Chỉ thêm `80/tcp` và `443/tcp` khi đã cấu hình nginx + TLS cho Grafana (xem
[DEPLOYMENT.md §4](../DEPLOYMENT.md#4-tls-for-grafana)).

## 3. Cài mã nguồn, thư mục logs và secrets

```bash
sudo git clone <REPOSITORY_URL> /opt/trading
sudo chown -R "$USER":"$USER" /opt/trading
cd /opt/trading
cp .env.example .env
chmod 600 .env

# TẠO THƯ MỤC LOGS VÀ CHOWN (BẮT BUỘC TRƯỚC KHI DỰNG DOCKER):
# docker-compose.yml mount ./logs:/app/logs cho collector và engine. Collector ghi
# logs/bars_closed.log, engine ghi logs/engine_alerts.log. Tiến trình trong container
# chạy với uid 10001 (appuser). Nếu không tạo trước, Docker daemon sẽ tự tạo thư mục
# thuộc root:root (755), tiến trình sẽ bị PermissionError khi ghi log,
# nuốt ngoại lệ và chạy tiếp im lặng làm mất toàn bộ bằng chứng chốt nến luồng và cảnh báo engine!
mkdir -p logs && sudo chown 10001:10001 logs

uv sync --frozen
```

Sửa `.env` bằng editor an toàn (`nano .env`). Điền đầy đủ năm biến `SSI_*`;
đặt `POSTGRES_PASSWORD` và `GRAFANA_ADMIN_PASSWORD` thành mật khẩu mạnh, không
dùng giá trị mặc định. Có thể tạo mật khẩu cục bộ bằng:

```bash
openssl rand -base64 32
```

Không đưa `.env`, private key SSI, token Telegram, nội dung token SSI hay output
có secrets vào Git, chat hoặc ticket. Xác minh file có quyền đúng:

```bash
stat -c '%a %U:%G %n' .env
# Kết quả mong đợi: 600 <nguoi-dung> <nhom> .env
```

Kiểm tra `config/config.yaml` trước khi chạy:

- `symbols`, `indices`, `holidays` đúng với kế hoạch vận hành.
- `real_trading_enabled: false`.
- Không sửa NATS URL trong Compose: các container đã dùng `nats://nats:4222`.

## 4. Khởi động và kiểm tra lần đầu

```bash
cd /opt/trading
docker compose config -q
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 collector
docker compose logs --tail=100 engine
```

`postgres` phải `healthy`; các service còn lại phải `running`. Mở dashboard qua
SSH tunnel, không công khai cổng 3000:

```bash
ssh -L 3000:127.0.0.1:3000 <USER>@<VPS_IP>
```

Sau đó vào `http://localhost:3000` trên máy cá nhân và đăng nhập bằng mật khẩu
Grafana đã đặt. Nếu cần truy cập từ Internet, xem chi tiết cấu hình nginx + Certbot
tại [DEPLOYMENT.md §4](../DEPLOYMENT.md#4-tls-for-grafana).

## 5. Lịch vận hành bắt buộc

**Khối cron nằm ở một nơi duy nhất: [DEPLOYMENT.md §9](../DEPLOYMENT.md#9-dead-mans-switch-heartbeat).**
Chép nguyên khối đó (gồm cả dòng `CRON_TZ=Asia/Ho_Chi_Minh`) vào `crontab -e`.

Trước đây file này giữ một **bản sao** của khối cron, và nó đã lệch thật: bản sao
chỉ còn 9 job trong khi `scripts/sched.sh` có 12 — thiếu `orderbook-recorder`
(ghi sổ lệnh VN30F trong phiên), `orderbook-daily-check` và `container-health`.
Ai dựng VPS theo bản sao này sẽ thiếu job mà không có dấu hiệu nào. Đó đúng là
bài học "một công thức hai bản thì sớm muộn lệch" (`4ea4c8d`) mà `sched.sh` đã
ghi ở đầu file, nên bản sao đã được bỏ.

`test_deployment_doc.py` buộc tập job trong `DEPLOYMENT.md` **bằng** tập job
trong `scripts/sched.sh`, nên khối ở đó không lệch âm thầm được.

```bash
crontab -e     # dán khối cron từ DEPLOYMENT.md §9
crontab -l     # kiểm lại: phải đủ 12 dòng job
```

Tạo thư mục backup và kiểm tra crontab:

```bash
sudo install -d -m 700 -o "$USER" -g "$USER" /var/backups/trading-db
crontab -l
```

SSI yêu cầu OTP thủ công mỗi ngày giao dịch. Trong khung 08:00–09:00, nạp token
vào DB theo [quy trình token SSI trong DEPLOYMENT.md §8.5](../DEPLOYMENT.md#85-ssi-token--quy-tr%C3%ACnh-ng%C3%A0y-giao-d%E1%BB%8Bch-depgap-1).
Không tự động hóa OTP; collector sẽ tự kết nối lại khi token hợp lệ có trong DB.

## 6. Theo dõi, backup và cập nhật

Mỗi ngày giao dịch, kiểm tra cảnh báo Telegram, `docker compose ps` và các file
trong `/opt/trading/logs/` (đặc biệt `logs/bars_closed.log`). Sau thay đổi source,
luôn cập nhật bằng:

```bash
cd /opt/trading
git pull --ff-only
uv sync --frozen
docker compose build collector engine
docker compose up -d --no-deps collector engine
docker compose ps
```

Không dùng `docker compose down -v`: lệnh này có thể xóa volume dữ liệu.
Để quay lại bản mã nguồn trước đó, checkout/switch đến commit đã biết tốt rồi
chạy lại các lệnh trên. Xác nhận image mới thực sự đã được dùng theo
[kiểm tra deployment drift trong DEPLOYMENT.md §10](../DEPLOYMENT.md#ph%C3%A9p-ki%E1%BB%83m-kh%C3%B4ng-h%E1%BA%BFt-h%E1%BA%A1n-so-m%E1%BB%91c-build-v%E1%BB%9Bi-commit-g%E1%BA%A7n-nh%E1%BA%A5t-ch%E1%BA%A1m-trading).

Backup phải được thử restore vào database scratch ít nhất một lần theo hướng dẫn
tại [DEPLOYMENT.md §6](../DEPLOYMENT.md#6-backups).

## 7. Tiêu chí bàn giao

Chỉ coi VPS sẵn sàng cho paper trading khi tất cả mục sau đều đạt:

- `docker compose ps` xanh sau reboot VPS.
- Grafana chỉ truy cập qua SSH tunnel hoặc HTTPS có xác thực.
- `.env` có mode `600`; mật khẩu mặc định đã bị thay.
- Thư mục `logs/` có quyền `10001:10001` và file `logs/bars_closed.log` được ghi thành công.
- Telegram nhận được cảnh báo thử từ heartbeat/dead-man switch.
- Cron thực sự tạo log trong `logs/` cho **mọi** job có trong `scripts/sched.sh` (đừng chép danh sách ra đây — nó đã lệch một lần; lấy danh sách bằng `scripts/sched.sh` gọi sai tham số, nó in đủ tên job).
- Có backup mới và restore thử thành công.
- `real_trading_enabled` vẫn là `false`.

Để chuyển sang lệnh thật, hoàn tất toàn bộ quy trình trong
[runbook diễn tập lệnh thật](superpowers/runbooks/dien-tap-lenh-that.md) và
[GO_LIVE_AUDIT.md](../GO_LIVE_AUDIT.md) trước; không chỉ thay đổi một cờ cấu hình.
