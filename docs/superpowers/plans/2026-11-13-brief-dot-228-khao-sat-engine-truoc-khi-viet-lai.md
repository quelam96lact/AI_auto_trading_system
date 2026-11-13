# Brief đợt 228: khảo sát engine trước khi dừng và viết lại theo nến ngày (CHỈ ĐỌC)

Ngày 13/11/2026. Người giao: Claude (Lead). Người làm: **Researcher**. Việc này chỉ đọc code, log và DB (SELECT). Không sửa gì.

## Bối cảnh

Chủ dự án quyết định ngày 13/11:

1. Bỏ chiến lược paper hiện tại trên 3 mã (HPG, IJC, AAA; `octopus_pullback` trên nến 5 phút).
2. Chuyển sang lọc mã có khối lượng lớn, đột biến trên **nến ngày**, giữ vài ngày, có học máy. Phần đo lợi thế là đợt 227 (Builder đang làm).
3. **Dừng engine cũ, giữ collector**, và viết lại engine song song với phép đo.

Lead cần một bản khảo sát để viết brief viết lại engine (đợt 229) và để dừng engine mà không gây báo động giả. Phiên kế tiếp là thứ Hai 16/11, nên phần A cần xong **trước 20:00 Chủ nhật 15/11**.

Việc này làm xen kẽ với đợt 226 (đo bộ nhớ postgres đêm nay). Đợt 226 ưu tiên hơn trong cửa sổ 01:45–03:15.

## Câu hỏi phải trả lời

### A. Dừng container engine thì cái gì kêu? (gấp)

Liệt kê **mọi** chỗ phụ thuộc vào việc engine đang chạy. Với mỗi chỗ, ghi `file:dòng`, điều kiện kích hoạt, giờ nào trong ngày nó kiểm, và tin sẽ gửi (mức, nội dung). Tối thiểu phải xét:

- `scripts/heartbeat_check.py`: danh sách `SERVICES`, nhịp engine, sổ sách engine (`engine_state`, `positions`), mọi nhánh khác có đọc dữ liệu của engine;
- `scripts/container_health_check.py`: container ở trạng thái `exited`, và container **không còn tồn tại**;
- `scripts/check_silent_engine.py` (engine-cam), `scripts/engine_consumer_check.py` (engine-consumer), `scripts/deploy_drift_check.py`, `scripts/check_golive_gate.py`, `scripts/host_preflight.py`, morning-summary;
- `trading/scheduler/` và `docker-compose.yml`: `depends_on`, `restart:`; Docker Desktop khởi động lại thì engine có tự chạy lại không;
- bảng Grafana và cảnh báo Grafana (nếu có) dùng dữ liệu engine;
- collector: có chỗ nào chờ hoặc phụ thuộc engine không (NATS consumer, stream).

Kết luận phần A phải là một bảng: "nếu chỉ `docker compose stop engine` thì các tin sau sẽ được gửi, vào các giờ sau". Kèm đề xuất cách dừng ít sửa nhất (ví dụ một cờ cấu hình "engine tắt có chủ đích" mà các job đọc). Chỉ đề xuất; Lead quyết.

### B. Engine hiện tại gắn với 3 mã và nến 5 phút ở đâu?

- Bản đồ `trading/engine/main.py` và `logic.py`: vòng lặp chính, nguồn nến (NATS subject), warm-up, chiến lược, quản lý rủi ro, đặt lệnh qua `PaperBroker`, ghi DB, khôi phục vị thế. Ghi `file:dòng` cho từng phần.
- Phần nào dùng lại được cho engine nến ngày nhiều mã (PaperBroker, phí, T+2, storage, cảnh báo), phần nào gắn chặt với stream 5 phút.
- `config/config.yaml`: `symbols` được ai đọc (collector, engine, heartbeat, các job kiểm). Đổi hoặc bỏ danh sách này thì ảnh hưởng những gì.
- Dùng GitNexus cho phần `trading/` (`node .gitnexus/run.cjs context|impact ... --repo .`, không npx). `scripts/` không được index, dùng grep.

### C. Trạng thái hiện tại trong DB (chỉ SELECT)

- Vị thế paper đang mở (`positions` có `qty != 0`), `engine_state` (tiền, lãi lỗ đã chốt), số lệnh paper từ 15/07.
- Các bảng engine ghi vào và job nào đọc chúng.
- **Không** in số tài khoản, token hay ID.

### D. Dữ liệu cho engine nến ngày

- `bars_daily` của phiên T có mặt trong DB lúc mấy giờ (job nào, lịch nào; đo trên 10 phiên gần nhất bằng log hoặc DB).
- Dữ liệu ngày có đủ cho khoảng 600–1.600 mã mỗi tối không; tỷ lệ mã thiếu nến của phiên gần nhất.
- Một job "quét cuối ngày" có thể đặt ở đâu trong hạ tầng hiện có (container scheduler, `sched.sh`), và các job cùng kiểu đang được canh thế nào.
- Lệnh mua ở open phiên sau: hệ thống hiện có nguồn giá mở cửa nào cho mã ngoài 3 mã đang stream.

## Cấm

- Không sửa file nào ngoài báo cáo. Không commit, không push, không `npx`.
- Không `docker compose stop/restart/up`, không chạy `sched.sh`, không chạy các script kiểm tra thật (chỉ đọc code của chúng). `--dry-run` cũng không chạy, vì có script vẫn ghi log.
- Không ghi DB. Không gọi API SSI/DNSE/BingX. Không gửi Telegram. Không đọc file token SDK hay `.env`.
- Không mở `data/research227/` và không đọc code `scripts/research227_*` (đợt 227 đang được niêm phong với bạn để phần engine không bị thiết kế theo kết quả đo).

## Tiêu chí hoàn thành

Báo cáo `docs/audit/2026-11-14-khao-sat-engine-truoc-khi-viet-lai.md`, gồm bốn mục A–D:

1. Mỗi khẳng định có `file:dòng` hoặc lệnh và output nguyên văn.
2. Phần A có bảng tin báo dự kiến và **danh sách đã đối chiếu đủ** các script trong `SCHEDULE_EXIT_POLICIES` (ghi rõ script nào đã đọc, script nào không liên quan engine và vì sao).
3. Tách rõ **đo được** với **suy luận**. Chỗ chưa đọc hết thì ghi "chưa kiểm", không khẳng định "không có".
4. Cuối báo cáo: danh sách câu hỏi mà Lead hoặc chủ dự án phải quyết trước khi viết lại engine.

Gửi Lead một tin ngắn khi xong phần A (không cần đợi B–D), và một tin khi xong toàn bộ.
