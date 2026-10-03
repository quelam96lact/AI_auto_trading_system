# Brief đợt 153 — diễn tập `DEPLOYMENT.md` trên một máy Ubuntu dùng xong bỏ

## Vì sao

Đích triển khai thật là VPS Ubuntu chạy 24/7. `DEPLOYMENT.md` dài hơn 1.100 dòng, đã sửa qua hàng chục đợt,
nhưng **chưa ai chạy nó từ đầu tới cuối trên Linux**. Đợt 139 chỉ chạy các nhánh Linux của
`host_preflight.py` bằng kịch bản giả lập. Riêng tuần này, Claude đã phải sửa ba lỗi tài liệu: giờ chạy chép
tay sai (đợt 149), liên kết chết và quy tắc mã thoát sai (audit 149). Ngày cắt chuyển, mỗi lỗi kiểu này là
một lần dừng giữa chừng trên máy thật.

Đợt này dựng một **container Ubuntu 24.04 đặc quyền** đóng vai VPS sạch, chạy Docker lồng bên trong, và làm
theo `DEPLOYMENT.md` **từng chữ**. Sản phẩm là một bảng: mỗi bước làm gì, ra gì, và tài liệu sai ở đâu.

**Agent không sửa `DEPLOYMENT.md`.** Mọi đề xuất sửa ghi vào báo cáo dưới dạng "chữ cũ → chữ mới". Claude
kiểm rồi mới sửa.

## Môi trường — Claude đã đo ngày 03/10

- Docker Desktop: 8 CPU, 8 GB RAM. Hệ thống thật đang dùng khoảng 530 MB; tổng giới hạn RAM của các container
  thật khoảng 3 GB.
- Container đặc quyền chạy được: Claude đã thử `docker:27-dind`.
- Đĩa C còn 166 GB, D còn 186 GB.
- Bản sao lưu thật mới nhất:
  `D:/My_Vault_Obsidian/Project/_backups/db/trading_20261003_020007.dump` (100 MB), kèm bản kê
  `trading_20261003_020007.counts`. Hai file này ở ngoài repo. **Chỉ mount chỉ-đọc**, không chép vào repo.

## Cách dựng — bắt buộc

1. **Container ngoài:** `ubuntu:24.04`, tên `vps-rehearsal`, cờ:
   - `--privileged --memory=4g --cpus=2`, để không giành RAM của hệ thống thật;
   - **không publish cổng nào** (`-p` bị cấm);
   - repo mount chỉ-đọc vào `/src`;
   - hai file sao lưu mount chỉ-đọc vào `/backup`.
2. **Mã nguồn:** `git clone /src /opt/trading`, thay cho `<repo-url>`. Cách này chỉ lấy những gì đã commit,
   đúng như VPS sẽ nhận. File nào thiếu vì chưa commit chính là một phát hiện.
3. **Secret:** `.env` tạo từ `.env.example`, điền **giá trị giả** (vd `SSI_CONSUMER_ID=fake`), để trống
   `TELEGRAM_*`. **Cấm chép, đọc hay mount `.env` thật**; cấm mở `scripts/.ssi_sdk_token.json`.
4. **Hai pha mạng:**
   - **Pha A (có mạng):** §1 (cài gói, uv), §2 (clone, `uv sync`), `docker compose build`.
   - Hết pha A: `docker network disconnect bridge vps-rehearsal`. Chứng minh đã mất mạng bằng một lệnh
     `curl` ra ngoài phải thất bại (vd tới `https://fc-data.ssi.com.vn`). Dán output.
   - **Pha B (không mạng):** mọi thứ còn lại.

   Lý do: bản sao lưu chứa bảng `ssi_auth_state`. Collector chạy trên dữ liệu khôi phục có thể dùng token SSI
   thật từ "máy thứ hai", đúng điều §11 cấm ("không chạy song song"). Cắt mạng là chốt chặn chính. Thêm một
   chốt nữa: ngay sau khi khôi phục, chạy `DELETE FROM ssi_auth_state` trong DB **của container diễn tập**,
   trước `docker compose up`.
5. **Docker bên trong:** container không có systemd, nên `systemctl enable --now docker` sẽ hỏng. Ghi đó là
   **LỆCH MÔI TRƯỜNG**, rồi chạy `dockerd` bằng tay. Làm tương tự với `timedatectl`, `ufw` và mọi thứ cần
   systemd hoặc kernel: thử đúng lệnh trong tài liệu, ghi kết quả, chỉ lách khi buộc phải lách.

## Phạm vi diễn tập

| Mục `DEPLOYMENT.md` | Làm gì |
|---|---|
| §1, §2 | Làm hết, đúng từng lệnh |
| §3 Firewall | Thử `ufw`. Không được thì ghi LỆCH MÔI TRƯỜNG |
| §4 TLS | **Không diễn tập** (cần tên miền thật) |
| §5 | `docker compose up -d --build`, rồi `docker compose ps` |
| §6 | Chạy `backup_db.sh` bên trong; khôi phục bản sao lưu thật theo đúng quy trình trong §6; chạy `restore_drill.py` và `backup_check.py` |
| §7, §8 | Kiểm giới hạn tài nguyên có hiệu lực (`docker inspect`); cài cấu hình logrotate theo tài liệu và chạy `logrotate -d` |
| §9 | Cài crontab **đúng như tài liệu ghi**, rồi chạy `crontab -l`. **Không đợi cron tự chạy.** Chạy tay từng job qua `scripts/sched.sh <job>`, kèm `--dry-run` ở job nào có cờ đó; job nào cần SSI thì ghi "cần mạng/SSI thật — không diễn tập". Chạy `host_preflight.py` trên Linux thật |
| §10 | Làm đúng quy trình dựng lại container sau khi sửa `trading/`: chạm một file trong bản clone, build lại, chạy phép kiểm deploy-drift |
| §11 | **Chỉ các bước phía VPS**: khôi phục từ bản sao lưu, đối chiếu số dòng với file `.counts`, và các bước còn lại làm được offline. **Không làm** các bước trên máy Windows (dừng task, dừng container thật). Bước kiểm kết nối SSI: không diễn tập |

**Kỳ vọng biết trước** (không phải lỗi tài liệu):
- Collector thất bại xác thực SSI vì credential giả và không có mạng.
- Ghi lại collector báo lỗi **thế nào**: có log và cảnh báo rõ ràng, hay chết im lặng? Đó là một quan sát
  quan trọng.

Ngoài collector, engine phải khởi động được và đọc NAV `0434226` từ DB khôi phục. Dán log dòng `NAV ...` của
engine.

## Giới hạn

- **Không đụng hệ thống thật.** Mọi lệnh `docker` của agent chỉ được nhắm vào `vps-rehearsal`, hoặc chạy
  **bên trong** nó. Cấm `docker compose` ở thư mục repo trên Windows, cấm `docker stop/rm/restart` với
  container `ai_auto_trading_system-*`.
  - Trong hôm nay Claude sẽ tự build lại và tạo lại container thật, nên thời điểm khởi động của chúng **sẽ**
    đổi. Đừng dùng thời điểm đó làm bằng chứng.
  - Bằng chứng là **danh sách đầy đủ các lệnh `docker` agent đã chạy trên host**, dán vào báo cáo.
- **Không commit, không push, không sửa file nào trong repo.** Ngoại lệ duy nhất là file báo cáo. Script
  diễn tập (nếu viết) để ở thư mục ngoài repo và dán nội dung vào báo cáo.
- Không sửa scheduled task. Không gửi Telegram. Không chạy gì có `--send`. Không dùng secret thật.
- **Theo dõi tài nguyên:** mỗi khoảng 30 phút trong lúc build/chạy, ghi `docker stats --no-stream` của các
  container thật. Postgres thật vượt 900 MiB thì **dừng diễn tập** (`docker stop vps-rehearsal`) và báo lại.
- **Hạn chót:** dọn sạch trước **22:00 Chủ nhật 04/10**. `docker rm -f vps-rehearsal` cùng mọi volume và
  image nó tạo **trên host**; image bên trong mất cùng container. Sau đó chứng minh bằng `docker ps -a`,
  `docker volume ls` và `docker system df` trước/sau.
- GitNexus không áp dụng: đợt này không sửa code.

## Tiêu chí hoàn thành

1. **Bảng theo từng mục §1–§11.** Mỗi lệnh tài liệu ghi gồm: lệnh nguyên văn, mã thoát, vài dòng output, và
   kết luận thuộc đúng một nhãn:
   - **ĐẠT**;
   - **LỖI TÀI LIỆU** (VPS thật cũng sẽ hỏng);
   - **LỆCH MÔI TRƯỜNG** (chỉ hỏng vì là container), ghi rõ vì sao chắc là do container;
   - **KHÔNG DIỄN TẬP**, kèm lý do.
2. **Khôi phục:** số dòng của từng bảng sau khi khôi phục, so với `trading_20261003_020007.counts`. Phải
   `>=` cho mọi bảng, cùng quy tắc của `restore_drill.py`.
3. **Stack bên trong:** output `docker compose ps`; log engine có dòng NAV; log collector khi thất bại xác thực.
4. **`host_preflight.py` trên Linux:** output đầy đủ.
5. **Danh sách lỗi tài liệu.** Mỗi lỗi có bằng chứng (output) và đề xuất "chữ cũ → chữ mới". Lỗi nào chỉ suy
   luận mà chưa chạy thì ghi rõ "chưa chạy".
6. **Bằng chứng dọn dẹp** và **danh sách lệnh docker trên host**.

## Báo cáo

`docs/superpowers/research/2026-10-04-dot-153-dien-tap-trien-khai-vps.md`: các bảng trên, nhật ký tài nguyên,
brief sai ở đâu, và cái gì không diễn tập được (kèm lý do).
