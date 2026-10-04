# Brief đợt 159 — thi hành quy ước `scripts/`, thay vì dọn tay một lần

## Bối cảnh — Claude đo ngày 04/10

Chủ dự án yêu cầu dọn rác codebase và image container. **Phần image Claude đã làm xong** (xem cuối brief).
Phần codebase thì số đo nói ngược với kỳ vọng: **rác rất ít**, và `scripts/README.md` **đã có** quy ước phân
loại cùng quy tắc "chỉ chủ dự án được xoá". Vậy việc cần làm không phải dọn tay, mà là **làm cho quy ước có
hiệu lực**.

**Đọc `scripts/README.md` trước tiên, cả 33 dòng.** Nó đã nói:
- `.probe_*`, `.spike_*`, `.repro_*` (có dấu chấm) = chỉ dùng ở máy dev, bị `.gitignore`, **không** lên VPS;
- không dấu chấm = công cụ vận hành/SDK chính thức;
- **"0 tham chiếu KHÔNG có nghĩa là bỏ đi được"** — phần lớn tham chiếu là chuỗi hướng dẫn trong thông báo
  lỗi, công cụ phân tích tĩnh không thấy;
- `backfill_universe.py` đọc **file dữ liệu** do một script spike sinh ra, chứ không `import` script đó;
- quy tắc 3: mọi đề xuất xoá phải thành danh sách kèm lý do, và **chỉ chủ dự án được xoá**.

### Số đo của Claude

| | Số |
|---|---|
| Script có dấu chấm (dev-only, đúng quy ước) | 20 |
| Script `.py` không dấu chấm trong `scripts/` | 116 |
| Trong đó: được `sched.sh` gọi | 14 |
| Trong đó: được `tests/` nhập hoặc gọi | 60 |
| **Không thuộc cả hai** | **39** |
| Trong 39 đó, mang tiền tố `spike_` / `probe_` / `measure_` mà **không** có dấu chấm | **23** |

Ví dụ cho thấy "mồ côi" không đồng nghĩa "rác" — bốn script, bốn kết luận khác nhau:

| Script | Sửa cuối | Số tài liệu nhắc |
|---|---|---|
| `check_real_order_readiness` | 03/10 | 9 — Claude vừa dùng ở đợt 150, công cụ sống |
| `probe_dead_man_switch` | 29/09 | 13 — công cụ đã tài liệu hoá |
| `verify_backup_restore` | 07/09 | 8 — bị `restore_drill` thay thế, nhưng xoá thì 8 tài liệu trỏ vào hư không |
| `spike_securities_status_check` | 26/09 | **0** |

### Lỗ thật

Quy ước nói "không dấu chấm = công cụ chính thức", nhưng **23 script mang tên nghiên cứu (`spike_`,
`probe_`, `measure_`) lại không có dấu chấm**, tức đang được ship vào git và lên VPS như công cụ chính thức,
mà không chỗ nào nói chúng chính thức ở điểm nào. Và **không có test nào thi hành quy ước**, nên script mồ
côi thứ 40 sẽ vào im lặng y như 39 cái trước.

## Việc 1 — khai báo tường minh, kèm bằng chứng

Thêm vào `scripts/README.md` một mục mới: bảng khai báo cho **mỗi** script không dấu chấm mà **không** được
`sched.sh` gọi và **không** được `tests/` dùng. Mỗi dòng gồm:
- tên script;
- **vai trò một câu**;
- **bằng chứng nó còn cần**: đường dẫn kèm số dòng của chỗ nhắc tới nó (thông báo lỗi, runbook, file dữ liệu
  nó sinh ra), hoặc đánh dấu **`KHÔNG RÕ`**.

**`KHÔNG RÕ` là một kết luận hợp lệ và được khuyến khích.** Đừng bịa lý do giữ lại cho đủ bảng. Bảng toàn
"giữ lại" không có bằng chứng thì vô giá trị, và sẽ làm test ở Việc 2 thành vô nghĩa.

Giữ nguyên ba mục đang có của `README.md`; chỉ **thêm**.

## Việc 2 — test thi hành quy ước

Thêm một test theo đúng khuôn đợt 142 ("mọi nhánh `sched.sh` phải thuộc `SCHEDULE_WATCH_JOBS` hoặc
`KHONG_CANH`"): mỗi script `.py` không dấu chấm trong `scripts/` phải thuộc **đúng một** trong ba nhóm:

1. được `scripts/sched.sh` gọi;
2. được `tests/` nhập hoặc gọi;
3. **có dòng khai báo trong bảng ở Việc 1**.

Không thuộc nhóm nào thì test **đỏ và nêu đúng tên file**. Bỏ qua `_*.py` (module dùng chung) và mọi file có
dấu chấm đầu tên.

→ kiểm chứng bằng phá thử: tạo `scripts/zzz_tam_thoi_dot159.py` rỗng → test đỏ, nêu đúng tên đó; xoá file đi,
test xanh lại. Và: xoá một dòng khỏi bảng khai báo → test đỏ, nêu đúng script đó.

## Việc 3 — đề xuất, KHÔNG thực hiện

Lập ba danh sách trong báo cáo. **Không xoá, không đổi tên file nào trong đợt này** — quy tắc 3 của
`scripts/README.md` và phân vai của `CLAUDE.md` đều nói chỉ Claude/chủ dự án được làm.

- **A. Nên thêm dấu chấm** (thành dev-only, rời khỏi git): script nghiên cứu một lần, số đo đã nằm trong một
  báo cáo ở `docs/superpowers/research/`. **Phải nêu báo cáo nào giữ số đo đó.**
- **B. Nên xoá**: không bằng chứng còn cần, **và** không tài liệu nào trỏ vào.
- **C. Nên giữ nhưng cần tài liệu hoá**: công cụ thật mà chưa có chỗ nào nói cách dùng.

**Cái bẫy của nhóm A, phải kiểm từng dòng:** `scripts/README.md` §2.1 nói công cụ **cần trên VPS phải không
có dấu chấm**. Thêm dấu chấm là lấy nó ra khỏi git, nên nó sẽ **không còn trên VPS**. Với mỗi đề xuất nhóm A,
nói rõ vì sao chắc chắn không ai cần nó trên máy chạy thật.

## Giới hạn

- **KHÔNG commit, KHÔNG push. KHÔNG xoá, KHÔNG đổi tên, KHÔNG di chuyển file nào.** Đợt này chỉ **thêm** tài
  liệu và test.
- **KHÔNG chạy lệnh `docker` nào.** Phần image Claude đã làm xong; daemon dùng chung với hệ thống đang chạy.
- **KHÔNG mở `scripts/.ssi_sdk_token.json`** và không in giá trị nào trong `.env`. Lưu ý: `scripts/*.json`
  có file token, nên **đừng glob** cả thư mục; lọc theo tên cụ thể. Hook của repo sẽ chặn, nhưng đừng thử.
- **Chỉ sửa:** `scripts/README.md` (thêm một mục) và một file test mới. Không sửa script nào, không sửa
  `sched.sh`.
- Chạy được bất cứ script nào để tìm hiểu thì **chỉ script chỉ-đọc**, và không script nào gửi Telegram,
  không `--send`, không chạm DB `trading` ngoài đọc.
- Trước khi chạy bộ đầy đủ:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng.

## Tiêu chí hoàn thành

1. **Bảng khai báo phủ hết** số script thuộc nhóm 3. Phép tính phải khớp:
   `14 (sched.sh) + 60 (tests) + <nhóm 3> = 113`, và `113 + 3 module _*.py = 116` tổng số `.py` không dấu
   chấm trong `scripts/` (Claude đã đếm 04/10). Dán phép tính. Con số của agent lệch so với 14/60/39 thì
   **nói rõ lệch ở script nào và vì sao** — có thể Claude đếm sai, đừng im lặng chỉnh cho khớp.
2. **Hai phá thử ở Việc 2**, ghi nguyên văn dòng đỏ, rồi dọn sạch file tạm (`git status` phải sạch trở lại).
3. **Số dòng `KHÔNG RÕ`** được nêu rõ. Bằng 0 thì phải giải thích vì sao cả 39 script đều có bằng chứng —
   Claude sẽ kiểm ngẫu nhiên 5 dòng, và một bằng chứng bịa sẽ bị bắt.
4. `ruff` sạch. `uv run pytest -q` ≥ **1.821 passed** cộng số test mới, 0 failed.
5. `git status` chỉ có: `scripts/README.md` đã sửa, file test mới, file báo cáo mới.

## Phần Claude đã làm — dọn image, ghi lại để không ai làm lại

Theo đúng §7 của `DEPLOYMENT.md`, và **không** dùng `prune -a` (cấm, vì nó xoá cả `:previous`):

| Việc | Kết quả |
|---|---|
| `docker image ls --filter dangling=true` (phép kiểm trước, vì `prune` không có `--dry-run`) | 8 image lớp build cũ; **không** cái nào là `:previous` |
| `docker image prune -f` | 36,28 MB |
| `docker builder prune -f --filter until=168h` | 45,39 MB |
| `docker volume rm <volume mồ côi>` | 43,5 MB — volume ẩn danh sinh 03/10 02:46, đúng lúc đợt 154 dựng container tạm kiểm image ghim |
| `docker rmi docker:27-dind` | 527 MB — còn lại từ buổi diễn tập đợt 153, repo không tham chiếu |

Tổng: image từ 20 còn 11, **3,741 GB → 2,98 GB**; volume từ 4 còn 3, phần thu hồi được về 0. Sáu container
vẫn chạy, và cả `collector:previous` lẫn `engine:previous` **còn nguyên**.

**Không xoá:** `ubuntu:24.04` (`scripts/probe_host_preflight_linux.sh:13` chạy nó thật),
`python:3.12-slim` (ảnh nền để build), `alpine` và `busybox` (tổng 20 MB, xoá không đáng vì có thể phải tải
lại), và tag `timescale/timescaledb:latest-pg16` — **nó trùng ID với `2.27.2-pg16`**, nên xoá tag không giải
phóng byte nào.

## Báo cáo

`docs/superpowers/research/2026-10-04-dot-159-thi-hanh-quy-uoc-scripts.md`: bảng khai báo, phép tính phủ,
ba danh sách đề xuất, brief sai ở đâu, cái gì không kiểm được.
