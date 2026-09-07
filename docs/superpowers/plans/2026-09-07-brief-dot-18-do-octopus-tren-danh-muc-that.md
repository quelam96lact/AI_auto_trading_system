# Brief đợt 18 — Đo octopus_pullback trên đúng 5 mã danh mục thật

Ngày giao: 07/09/2026
Base: `9f913ac` (main), cây làm việc sạch, 609 test xanh, ruff sạch.
Người giao: Claude (planner/auditor).

---

## 1. Vì sao đợt này, và vì sao KHÔNG phải một trong ba quyết định lớn

Ba việc lớn đang treo — Tier 1 (chiến lược có edge không), Q-2 (tài khoản/rổ mã lệch
nhau), Q-3 (mô hình xác nhận lệnh) — đều là **quyết định của chủ dự án**, không phải việc
giao được cho agent. Đợt này không đụng vào cả ba.

Nhưng có một khoảng trống dữ liệu nằm **giữa** Tier 1 và Q-2, thuần đo lường, không quyết
định gì cả: **octopus_pullback (khung ngày) chưa từng được đo trên đúng 5 mã mà tài khoản
thật đang nắm giữ.**

Mọi con số "không có edge" đo được từ trước tới nay đều trên rổ khác:

| Đợt | Đo trên | Kết quả |
|---|---|---|
| 4 | 439 mã lọc thanh khoản (rổ chung) | PF 0,74, 1.514 lệnh, −1.615.319.902 VND |
| 11 | 310 mã 5m (rổ chung) | PF 0,47, 574 lệnh |

Danh mục thật (đo lại 07/09, tài khoản 0434226) là **FOX, HCM, SSI, TCX, VCB** — không mã
nào trong hai bảng trên. Dữ liệu đã đủ để đo:

```
symbol | so ngay bar | tu     | den
FOX    | 2405        | 2017   | 2026-09-06
HCM    | 2665        | 2016   | 2026-09-06
SSI    | 2665        | 2016   | 2026-09-06
TCX    | 217         | 2025-10| 2026-09-06   (mới niêm yết, vẫn đủ warmup 20 ngày)
VCB    | 2663        | 2016   | 2026-09-06
```

Giá trị của phép đo này: nếu Q-2 được quyết theo hướng đổi `real_order_account` sang
0434226 và đổi `symbols` theo danh mục thật, thì câu hỏi kế tiếp lập tức là "chiến lược có
edge trên 5 mã đó không". Đo trước thì khi quyết định tới, dữ liệu đã có sẵn. Đây **không**
phải bước dọn đường để tự ý đổi `symbols` — brief này **không đụng `config.yaml`**.

---

## 2. Ràng buộc

- `real_trading_enabled` giữ `false`. Không đổi. Không gọi SSI — backtest chỉ đọc DB.
- Không in secret. `.env` không sửa, không commit. `config/config.yaml` **không sửa**.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB `trading`. Đợt này chỉ `SELECT`.
- **Không sửa** `PaperBroker`, `run_backtest`, `derivative_backtest`.
- Chỉ sửa file được nêu tên. Phát hiện ngoài phạm vi: báo cáo, không tự sửa.
- **KHÔNG xoá file nào, không commit, không push.**
- **Không kết luận thay chủ dự án.** Báo cáo chỉ trình bày số đo. Không viết câu kiểu "nên
  đổi tài khoản" hay "chiến lược nên bỏ" — đó là việc của mục 7 mà tôi (Claude) sẽ viết sau
  khi có số, không phải của agent.

**GitNexus:** `npx gitnexus analyze` trước khi sửa và sau khi xong, kèm `gitnexus_impact`
cho symbol bạn chạm (đặc biệt `main()` trong `scripts/measure_strategy.py` — đây là script
đã dùng để tái lập hard-gate, xem mục 3.1) và `gitnexus_detect_changes()`. `analyze` sẽ tự
sửa dòng đếm trong `AGENTS.md`/`CLAUDE.md` — bình thường, đừng revert, đừng commit.

---

## 3. Task 1 — Thêm bộ lọc `--symbols` vào `scripts/measure_strategy.py` (additive, không đổi hành vi mặc định)

**File được sửa:** `scripts/measure_strategy.py`.

### 3.1. Vì sao sửa file này thay vì viết script mới

`scripts/measure_strategy.py` là script đã tạo ra baseline hard-gate
(−1.615.319.902 VND / 1.514 lệnh / 439 mã, đợt 4) và đã qua một đợt chuẩn hoá riêng (đợt 9,
9b). Nó đã có `--limit` và `--exclude-file` làm bộ lọc mã theo kiểu **loại bớt**. Thêm
`--symbols` là bộ lọc kiểu **chọn đúng** — cùng họ, cùng vị trí trong code, đúng tinh thần
"một công thức, một chỗ": không tạo thêm một `measure_octopus_*.py` thứ 12 chỉ để đổi danh
sách mã (repo đã có khá nhiều file dạng đó — xem đợt 17).

**Vì đây là script hard-gate**, thay đổi phải **additive tuyệt đối**: khi không truyền
`--symbols`, hành vi và output phải giống hệt trước — Task 2 của phần kiểm chứng dưới đây
bắt buộc chứng minh điều này bằng cách tái lập nguyên số hard-gate.

### 3.2. Yêu cầu

Thêm một tham số dòng lệnh:

```python
ap.add_argument(
    "--symbols",
    default=None,
    help="danh sách mã cách nhau bởi dấu phẩy (vd: FOX,HCM,SSI). "
         "Khi truyền, BỎ QUA --limit và --exclude-file, chỉ đo đúng các mã này.",
)
```

Logic lọc: nếu `args.symbols` được truyền, `symbols` = danh sách đó (upper-case, giữ đúng
thứ tự người dùng gõ), **không** áp dụng `--limit` hay `--exclude-file` lên nó (đo đúng
mã được chỉ định, không lọc thêm). Nếu không truyền, giữ nguyên logic cũ (đọc từ
`bars_daily`, áp `--exclude-file` rồi `--limit`).

Không đổi bất cứ dòng nào khác trong `main()` — không đổi `measure_one`, `liquidity_spec`,
phần tính tổng hợp, phần in báo cáo.

### 3.3. Kiểm chứng — bắt buộc tái lập hard-gate KHÔNG lệch một đồng

```
uv run python scripts/measure_strategy.py --strategy octopus_pullback --exclude-file exclusions.txt
```

(câu lệnh gốc, nguồn: `docs/superpowers/research/2026-09-05-dot-4-q-r-report.md:31`;
`exclusions.txt` đã có sẵn ở gốc repo, 246 dòng — không cần tự tạo). Phải ra **đúng**
`-1.615.319.902` / `1.514` lệnh / `439` mã — như bảng ở mục 1. Lệnh này chạy trên toàn bộ
`bars_daily` (gần 3 triệu dòng) nên **mất vài phút, không phải vài giây** — đừng ngắt sớm
tưởng là treo.

**Nếu lệch dù chỉ một đồng: dừng lại, đừng đi tiếp sang Task 2, báo cáo số lệch và dòng
lệnh đã chạy.** Đây là tín hiệu bạn đã vô tình đổi hành vi mặc định.

Sau khi tái lập đúng, chạy thử `--symbols` trên một tập nhỏ đã biết trước (ví dụ 3 mã
`VCB,HPG,TCB` — nhắc tới trong đợt 4 như "quan sát ban đầu") và xác nhận số mã trong output
đúng bằng 3, không bị `--limit`/`--exclude-file` mặc định chi phối.

---

## 4. Task 2 — Chạy đo trên đúng 5 mã danh mục thật, lưu báo cáo

**File được tạo:** `docs/superpowers/research/2026-09-07-dot-18-octopus-daily-danh-muc-that.md`
(chỉ file này được tạo mới; không sửa file nào khác ngoài Task 1).

### 4.1. Lệnh chạy

```
uv run python scripts/measure_strategy.py --strategy octopus_pullback \
  --symbols FOX,HCM,SSI,TCX,VCB
```

Dùng nguyên `DEFAULT_CAPITAL`, `DEFAULT_FROM`, `DEFAULT_TO` của script (không truyền
`--capital`/`--from`/`--to`) — để con số có thể so sánh trực tiếp với baseline đợt 4, vốn
cũng dùng mặc định của chính script này.

### 4.2. Nội dung báo cáo

Dán **nguyên văn** output của lệnh trên — không tóm tắt, không tự gõ lại bảng số liệu. Sau
đó viết đúng ba mục ngắn, **không thêm kết luận/khuyến nghị**:

1. **Số đo tổng hợp**: PnL chiến lược, PnL buy-and-hold, số lệnh, số mã có lệnh, số mã
   "liquid" theo cổng thanh khoản của `octopus_pullback` (mã nào không đạt ngưỡng thanh
   khoản `min_avg_value_20` sẽ có `liquid=False`, `trades=0` — đây là kết quả hợp lệ, không
   phải lỗi, cứ báo cáo nguyên vậy).
2. **Bảng từng mã** (5 dòng): symbol, số lệnh, PnL chiến lược, PnL buy-and-hold, liquid hay
   không — lấy đúng từ output, không tính lại.
3. **Đối chiếu với hai baseline đã có** (bảng ở mục 1 của brief này) — chỉ nêu con số cạnh
   nhau, không bình luận "tốt hơn" hay "tệ hơn".

### 4.3. Kiểm chứng

- Chạy lệnh **hai lần liên tiếp**, xác nhận output giống hệt nhau (backtest phải xác định —
  cùng input phải ra cùng output). Dán lần chạy thứ hai làm bằng chứng, không cần dán vào
  báo cáo chính, chỉ cần nêu "đã chạy lại lần 2, khớp tuyệt đối với lần 1".
- Không có bước sabotage cho Task 2 — đây là chạy đo, không phải thêm logic mới cần chứng
  minh có răng. Task 1 mới cần sabotage-style kiểm chứng (mục 3.3 — tái lập hard-gate).

---

## 5. Báo cáo nghiệm thu phải có

1. Output thô của lệnh tái lập hard-gate (Task 1, mục 3.3) — phải khớp `-1.615.319.902` /
   `1.514` / `439` **chính xác**.
2. Output thô của lệnh thử `--symbols VCB,HPG,TCB` — xác nhận đúng 3 mã.
3. File báo cáo Task 2, đường dẫn đầy đủ.
4. `uv run pytest -q` (toàn bộ suite) — 0 failed. Đây thuần thêm một tham số CLI, không nên
   ảnh hưởng gì, nhưng vẫn phải chạy và dán bằng chứng.
5. `uv run ruff check trading tests scripts` — sạch.
6. `git status --short` + `git diff --stat`. File được phép: `scripts/measure_strategy.py`
   (sửa), `docs/superpowers/research/2026-09-07-dot-18-octopus-daily-danh-muc-that.md`
   (mới), cộng `AGENTS.md` + `CLAUDE.md` (do `analyze` sinh). File nào khác là lỗi.
7. GitNexus: hai lần `analyze`, `gitnexus_impact`, `gitnexus_detect_changes`.
8. Phát hiện ngoài phạm vi: liệt kê, không sửa.

**Output thô, nguyên văn.** Nhiều đợt trước từng có mô tả trong báo cáo không khớp mã/kết
quả thật dù code đúng — tôi sẽ chạy lại tất cả và đối chiếu từng con số.

---

## 6. Tiêu chí "xong"

- [ ] `npx gitnexus analyze` chạy trước và sau.
- [ ] `--symbols` là additive: không truyền thì hành vi giống hệt cũ, đã chứng minh bằng
      tái lập đúng số hard-gate.
- [ ] `--symbols FOX,HCM,SSI,TCX,VCB` chạy được, output ổn định qua 2 lần chạy.
- [ ] Báo cáo Task 2 có đủ 3 mục, không có câu kết luận/khuyến nghị.
- [ ] Toàn bộ suite xanh, ruff sạch.
- [ ] Không sửa `config.yaml`, không gọi SSI, không xoá file nào.
- [ ] Chưa commit, chưa push.

---

## 7. Việc của chủ dự án — không đổi so với các đợt trước

Không có mục mới. Danh sách vẫn là: rebuild image, tạo task `trading-engine-cam`, Docker
tự khởi động, quan sát token qua mốc 03:05 sáng, dọn 10 image Docker cũ, và ba quyết định
lớn (Tier 1, Q-2, Q-3) — đợt 18 chỉ **cung cấp thêm dữ liệu** cho Q-2, không tự quyết thay.
