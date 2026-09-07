# Quét toàn bộ codebase + Brief đợt 17 — Mắt xích ẩn của universe

Ngày: 07/09/2026
Base: `b37afd8` (main), cây làm việc sạch, 608 test xanh, ruff sạch.
Người viết: Claude (planner/auditor).

---

## 1. Kết luận trước, chi tiết sau

**Codebase này không nhiều rác.** Tôi quét toàn bộ và phải nói thẳng: những thứ tôi kỳ vọng
tìm thấy thì hầu hết đã sạch từ trước. Cụ thể, các phép đo cho kết quả **không có vấn đề**:

| Đã kiểm | Kết quả |
|---|---|
| `TODO`/`FIXME`/`HACK` trong `trading`, `scripts`, `tests` | **0** |
| Hàm công khai trong `trading/` không ai gọi | **đúng 1** (xem mục 3.4) |
| Module trong `trading/` không ai tham chiếu | **0** |
| Hằng số phí bị chép nhiều nơi | tập trung ở `paper_broker.py`, 8 script đều `import` — **1 ngoại lệ**, xem 3.3 |
| Công thức Sharpe bị chép | tập trung ở `trading/metrics.py`, mọi nơi đều gọi lại — **sạch** |
| Phụ thuộc thừa trong `pyproject.toml` | **0** (`ssi-fc-data` vẫn được `feed.py` dùng thật) |
| `ruff check trading tests scripts` | sạch |
| Rác spike bị commit nhầm | **0** — `.gitignore` đã gom 25 dòng liệt kê tay thành pattern từ 01/09 |

Nên **giá trị của lần quét này không nằm ở danh sách file cần xoá.** Nó nằm ở một thứ khác,
và thứ đó nghiêm trọng hơn nhiều:

> **Có một mắt xích sản xuất treo trên một file `.gitignore` không có trong git.**
> Trên bản clone mới — tức là trên VPS — job nạp dữ liệu hằng đêm sẽ chết ngay lần chạy đầu.

Và trớ trêu: mắt xích đó nấp sau một cái tên có tiền tố `spike_`, tức là **đúng thứ mà một
đợt "dọn rác" theo tên file sẽ xoá đầu tiên.**

---

## 2. Phát hiện chính — chuỗi mắt xích ẩn

### 2.1. Bằng chứng

`scripts/backfill_universe.py:44-52`:

```python
def load_symbols(cfg, storage, exchanges: set[str] | None = None) -> list[str]:
    """Đọc .spike_all_symbols_classified.json (Task 4b), lọc CỔ PHIẾU đúng: ..."""
    path = Path(__file__).parent / ".spike_all_symbols_classified.json"
    if not path.exists():
        raise SystemExit("Chua co .spike_all_symbols_classified.json - chay Task 4b truoc")
```

Trạng thái file đó, đo hôm nay:

```
$ git check-ignore -v scripts/.spike_all_symbols_classified.json
.gitignore:16:scripts/.spike_*.json    scripts/.spike_all_symbols_classified.json

$ git ls-files scripts | grep all_symbols
(rỗng — KHÔNG có trong git)

$ ls -l scripts/.spike_all_symbols_classified.json
1.15 MB, sửa lần cuối 09/08/2026
```

Ghép lại:

1. `backfill_universe.py` là **job hằng đêm** — scheduled task `trading-backfill-universe`,
   chạy 20:30, nạp `bars_daily` và duy trì `symbol_universe`.
2. Nó **cứng đầu vào** ở một file JSON 1,15 MB.
3. File đó **bị `.gitignore` loại**, không nằm trong git, chỉ tồn tại trên máy dev này, và
   đã một tháng không đổi.
4. Người sinh ra file đó là `scripts/spike_ssi_symbols_classify.py` — script mà phép đo
   tham chiếu theo tên cho ra **0 kết quả trên toàn repo**. Nghĩa là nó trông y hệt một
   spike vứt đi.

### 2.2. Hai hệ quả

**Hệ quả A — VPS.** Clone repo lên Ubuntu, chạy `sched.sh backfill`: `SystemExit`. Không có
bar ngày nào được nạp. `DEPLOYMENT.md:343` có nói `--use-universe` đọc `symbol_universe`,
nhưng **không chỗ nào nói `symbol_universe` được nạp từ đâu**. Đây là một lỗ hổng cứng của
đường di trú VPS mà đợt 13/14 không chạm tới — hai đợt đó kiểm đường **sao lưu/phục hồi dữ
liệu**, không kiểm đường **dựng lại từ mã nguồn**.

**Hệ quả B — bẫy dọn rác.** Nếu ai đó (người hay agent) dọn `scripts/` theo tiền tố
`spike_`, họ xoá mất cái máy sinh ra file, và thông báo lỗi còn lại thì chỉ trỏ tới
`"Task 4b"` — một số hiệu task từ brief cũ, không tra được ở đâu trong repo nữa.

### 2.3. Ba script khác cũng đội lốt "spike"

Cùng phép đo cho thấy tiền tố `spike_` đang nói dối ở nhiều chỗ:

| Script | Thực chất là gì | Bằng chứng |
|---|---|---|
| `spike_ssi_sdk_auth.py` | **Công cụ khôi phục OTP của vận hành** | được trỏ tới từ `trading/collector/ssi_auth.py:65`, `scripts/heartbeat_check.py`, `scripts/load_token_to_db.py`, `tests/test_ssi_auth.py`, và `RUNBOOK_OTP_AUTH.txt` |
| `spike_ssi_symbols_classify.py` | **Máy sinh universe cho job hằng đêm** | mục 2.1 |
| `spike_ssi_sdk_derivative_ohlc_stream.py` | sinh fixture mà test đọc | được `trading/collector/backfill.py` nhắc tới; output là ngoại lệ `!` duy nhất trong `.gitignore` |

Ba file này **không được xoá**. Vấn đề của chúng là cái tên, không phải sự tồn tại.

### 2.4. Ứng viên xoá thật — chỉ còn 3, và giá trị thấp

Sau khi loại hết những cái trên, số file thực sự không ai dùng:

| File | Tham chiếu trên toàn repo |
|---|---|
| `scripts/spike_ssi_sdk_index_summary.py` | 0 |
| `scripts/spike_securities_summary_raw.py` | 0 |
| `scripts/spike_ssi_sdk_index_lookup.py` | 1 — chỉ là một dòng chú thích trong `spike_ssi_sdk_index_stream.py` |

Cả ba đều thuộc mảng chỉ số (VNINDEX/VN30) đang **tạm dừng có chủ đích** (xem 3.4). Tôi
**không giao xoá** — git đã giữ lịch sử, xoá 3 file nhỏ gần như không đem lại gì, mà lại
tạo rủi ro nhỏ khi mảng chỉ số được nối lại. Nếu anh muốn xoá thì nói, tôi giao riêng.

---

## 3. Những thứ trông như rác nhưng không phải

Ghi lại để lần quét sau khỏi mất công đo lại.

### 3.1. `docs/` — 194 file, giữ nguyên

Đây là sổ ghi của dự án: 136 file `docs/superpowers`, 50 `docs/prompts`, 7
`docs/plans-legacy`. Toàn văn bản, không tốn gì đáng kể, và là thứ duy nhất truy được vì
sao từng quyết định được đưa ra. **Xoá là lỗ ròng.** Không giao.

### 3.2. `.gitnexus/` — 253 MB, nhưng chỉ được loại bởi luật cục bộ

Thư mục cache của GitNexus chiếm 253 MB trong 266 MB của cây làm việc. Nó **có** bị loại,
nhưng bằng `.git/info/exclude:7` — file **cục bộ, không nằm trong git**.

Nghĩa là trên bản clone mới, `.gitnexus/` không được loại. Ai chạy `git add -A` sau khi
`npx gitnexus analyze` sẽ nạp 253 MB vào lịch sử. → Task 2.

### 3.3. `FEE_RATE_ESTIMATE` — bản sao thứ hai của một con số đã có chủ

`scripts/confirm_real_order.py:26`:

```python
FEE_RATE_ESTIMATE = 0.0025  # 0.25% giá trị lệnh — biểu phí SSI công khai, đặt lệnh
```

Cùng con số với `trading/paper_broker.py:12 FEE_RATE = 0.0025`, gán bằng literal riêng.

Đây là đường **tiền thật** — `confirm_real_order.py` dùng nó để ghi `fee` vào
`real_order_fills`. Repo đã trả giá đúng cho loại lỗi này một lần: một literal `0.0015`
không nguồn từng làm hỏng cả hai hard gate (xem `paper_broker.py`). → Task 3.

### 3.4. `Storage.write_index_values` — chết, nhưng chết có chủ đích

`trading/storage/db.py:153` là hàm công khai duy nhất trong `trading/` không ai gọi. Bảng
`index_values` có **0 dòng**.

Nhưng đây không phải tai nạn: `trading/collector/feed.py:195` và
`trading/collector/main.py:119` đều có chú thích *"KHÔNG map IndexValue cho tới khi có
nguồn dữ liệu thật khác"*. Parser vẫn sinh `IndexValue` và vẫn có test. Cái đang thiếu là
nguồn dữ liệu, không phải mã.

**Không xoá.** Chỉ cần một dòng chú thích nối nó về quyết định tạm dừng, để lần quét sau
không phải điều tra lại từ đầu. → Task 4.

### 3.5. Không phải việc của agent — dọn máy

- 10 image Docker `autotrading-*` từ 07/06/2026 còn nằm lại (`docker images`). Xoá bằng
  `docker image rm` khi anh rảnh.
- Container `nats-test` đang chạy ngoài lúc chạy test.

Cả hai là dọn máy, không phải sửa repo. Tôi không giao cho agent.

---

## 4. Brief đợt 17 — giao agent

### Ràng buộc

- `real_trading_enabled` giữ `false`. **Không gọi SSI một lần nào** — cả 4 task đều không cần.
- Không in secret. `.env` không sửa, không commit. `config/config.yaml` không sửa.
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB `trading`.
- Không sửa định nghĩa `PaperBroker`, `run_backtest`, `derivative_backtest`.
- **Chỉ sửa file được nêu tên trong từng task.** Phát hiện ngoài phạm vi: báo cáo, không tự sửa.
- **KHÔNG xoá file nào** trong đợt này. Kể cả 3 file ở mục 2.4 — tôi đã cân nhắc và cố ý
  không giao. Nếu bạn thấy file khác đáng xoá: **liệt kê trong báo cáo**, đừng xoá.
- **KHÔNG commit, KHÔNG push.**

**GitNexus:** `npx gitnexus analyze` **trước** khi sửa và **sau** khi xong, kèm
`gitnexus_impact` cho symbol bạn chạm và `gitnexus_detect_changes()`. `analyze` sẽ tự sửa
dòng đếm trong `AGENTS.md` và `CLAUDE.md` — bình thường, không phải vi phạm phạm vi, đừng
revert, đừng commit. MCP không kết nối được thì vẫn chạy CLI và nói thẳng phần nào thiếu.

---

### Task 1 — Gỡ mắt xích ẩn của universe

**File được sửa:** `.gitignore`, `scripts/backfill_universe.py`, `DEPLOYMENT.md`,
`tests/test_backfill_universe.py` (**đã có sẵn** — thêm test vào đó, đừng tạo file mới).

Ba việc, làm đủ cả ba:

**1a. Đưa file dữ liệu vào git.** Thêm ngoại lệ trong `.gitignore`:

```
!scripts/.spike_all_symbols_classified.json
```

đặt **ngay sau** dòng ngoại lệ đã có cho `.spike_derivative_ohlc_5m_2m_sample.json`, và
viết chú thích cùng kiểu: nói rõ đây là **đầu vào bắt buộc của job hằng đêm**, không phải
rác spike. Rồi `git add` chính file đó (1,15 MB).

> **Vì sao commit chứ không sinh lại trên VPS:** sinh lại cần xác thực SSI và một lượt gọi
> API; commit thì bản clone chạy được ngay, không thêm nhánh mã nào, và đã có tiền lệ đúng
> hình dạng này (`.spike_derivative_ohlc_5m_2m_sample.json`, commit `cc8048e`). Đổi lại:
> file sẽ cũ dần — chấp nhận, vì `symbol_universe` vốn không đổi hằng ngày, và Task 1c làm
> cho việc làm mới nó tra được.

**1b. Sửa thông báo lỗi cho tra được.** Câu hiện tại
`"Chua co .spike_all_symbols_classified.json - chay Task 4b truoc"` trỏ tới một số hiệu
task không còn tồn tại ở đâu. Thay bằng câu nêu **đúng lệnh cần chạy** để sinh lại file
(tên script sinh ra nó), và nói rõ script đó cần xác thực SSI.

**1c. Vá `DEPLOYMENT.md`.** Mục quanh dòng 343 nói `--use-universe` đọc `symbol_universe`
nhưng không nói `symbol_universe` được nạp từ đâu. Thêm đúng một đoạn ngắn: chuỗi
`spike_ssi_symbols_classify.py` → `.spike_all_symbols_classified.json` →
`backfill_universe.py --use-universe` → `symbol_universe`, kèm câu "file JSON đã nằm trong
git nên bản clone mới chạy được ngay".

**Kiểm chứng:**

| # | Phép | Phải thấy |
|---|---|---|
| 1.1 | `git check-ignore -v scripts/.spike_all_symbols_classified.json` | **không** còn bị loại (lệnh trả về rỗng, exit khác 0) |
| 1.2 | `git ls-files scripts \| grep all_symbols` | file đã được theo dõi |
| 1.3 | `git check-ignore -v scripts/.spike_all_symbols.json` | **vẫn** bị loại — ngoại lệ chỉ mở đúng một file, không mở cả họ |
| 1.4 | Test mới (xem dưới) | xanh |

**Test bắt buộc** trong `tests/test_backfill_universe.py`: khẳng định
`scripts/.spike_all_symbols_classified.json` **tồn tại** và `json.loads` được, có khoá
`boards`, và ít nhất một mục có cả `symbol`, `listed_shares`, `cw_underlying_symbol` — tức
đúng ba trường `load_symbols` đọc. Đây là lớp chống việc file bị xoá hoặc bị `.gitignore`
nuốt lại lần nữa.

→ **Sabotage:** đổi tên file trên đĩa (`git mv` sang tên khác) ⇒ test phải **đỏ**. Dán tên
test đỏ + dòng lỗi. Rồi đổi lại và chạy xanh.

**Không được làm:** không đổi thuật toán lọc trong `load_symbols` (`listed_shares > 0 AND
cw_underlying_symbol is null`). Không đổi tên file JSON, không đổi tên script sinh ra nó —
đổi tên chạm nhiều tài liệu, để riêng.

---

### Task 2 — Chuyển luật loại `.gitnexus/` từ cục bộ sang cam kết

**File được sửa:** `.gitignore`.

`.gitnexus/` đang chỉ bị loại bởi `.git/info/exclude` — file không nằm trong git, nên bản
clone mới không có luật này, và 253 MB cache có thể bị `git add -A` nuốt vào.

Thêm `.gitnexus/` vào `.gitignore` kèm chú thích ngắn (cache của công cụ, ~253 MB, không
bao giờ commit). **Không đụng `.git/info/exclude`** — để nguyên, thừa một chút vô hại.

**Kiểm chứng:** `git check-ignore -v .gitnexus/lbug` phải trỏ tới **`.gitignore`**, không
còn trỏ `.git/info/exclude`. Dán output.

---

### Task 3 — Xoá bản sao thứ hai của phí

**File được sửa:** `scripts/confirm_real_order.py`, `tests/test_confirm_real_order.py`.

Bỏ literal ở dòng 26, thay bằng import từ nguồn có chủ:

```python
from trading.paper_broker import FEE_RATE
```

Giữ tên `FEE_RATE_ESTIMATE` như một bí danh (`FEE_RATE_ESTIMATE = FEE_RATE`) để không phải
sửa chỗ dùng, và giữ nguyên chú thích giải thích vì sao đây là **ước lượng** (SSI không trả
phí theo từng lệnh) — chú thích đó vẫn đúng và vẫn cần.

**TUYỆT ĐỐI KHÔNG làm điều này:** hai test ở `tests/test_confirm_real_order.py:216` và
`:269` khẳng định `fee` bằng literal `0.0025` viết tay. Trông như "bản sao thứ ba" của con
số, và bạn sẽ bị cám dỗ import `FEE_RATE` vào test cho "nhất quán". **Đừng.** Literal trong
test chính là thứ làm cho test có răng: nếu test cũng import hằng số, thì đổi `FEE_RATE`
xong test vẫn xanh, và ta mất đúng cái chuông muốn giữ. Test phải neo giá trị kỳ vọng độc
lập với mã sản xuất. Giữ nguyên hai literal đó.

**Kiểm chứng:**

1. `tests/test_confirm_real_order.py` toàn bộ xanh — hai test kiểm `fee` đã có sẵn ở đó.
2. **Sabotage:** đổi `trading/paper_broker.py` `FEE_RATE` thành `0.0015` ⇒ hai test tính
   `fee` trong `test_confirm_real_order.py` phải **đỏ**, chứng minh `confirm_real_order.py`
   thật sự đọc từ nguồn chung chứ không còn literal riêng. Dán tên test đỏ + dòng lỗi.
   Khôi phục **bằng cách sửa ngược đúng chỗ đó** — **không dùng `git checkout --`** (nó xoá
   luôn việc chưa commit; tôi đã tự vấp ở đợt 15).
3. Sau khôi phục: `git diff trading/paper_broker.py` **rỗng**.
   *(Đừng kiểm bằng `git diff trading/` — Task 4 có thêm chú thích vào
   `trading/storage/db.py`, nên cả thư mục sẽ không rỗng. Chỉ file này phải rỗng.)*

---

### Task 4 — Dán nhãn cho những thứ trông như rác

**File được sửa:** `scripts/spike_ssi_sdk_auth.py`,
`scripts/spike_ssi_symbols_classify.py`,
`scripts/spike_ssi_sdk_derivative_ohlc_stream.py`, `trading/storage/db.py`.

Thêm **một khối chú thích ngắn ở đầu** mỗi file script (2-4 dòng, không phải bài luận), nội
dung: *đây KHÔNG phải spike vứt đi*, ai tiêu thụ nó, và điều gì hỏng nếu xoá. Dùng đúng
bằng chứng ở mục 2.3 của brief này.

Với `trading/storage/db.py:153` (`write_index_values`): thêm **một dòng** trong docstring
nói rõ hàm này chưa có người gọi vì mảng chỉ số đang tạm dừng, và trỏ tới
`trading/collector/feed.py` (chú thích *"KHÔNG map IndexValue cho tới khi có nguồn dữ liệu
thật khác"*). Mục đích: lần quét dead code sau không phải điều tra lại.

**Không đổi một dòng mã thực thi nào trong task này** — chỉ chú thích.

**Kiểm chứng:** `git diff` của task này chỉ gồm dòng chú thích; toàn bộ suite vẫn 608 xanh;
ruff sạch.

---

## 5. Báo cáo nghiệm thu phải có

1. Output thô của **cả 4 phép** ở Task 1, **cả 2** ở Task 2.
2. Output sabotage nguyên văn của Task 1 và Task 3, kèm **tên test đỏ thật**.
3. `uv run pytest -q` (**toàn bộ** suite, không thay bằng `-m "not integration"`) — phải
   **0 failed**. Dán dòng tổng kết.
4. `uv run pytest -q -m "not integration"` — để đối chiếu.
5. `uv run ruff check trading tests scripts` — sạch.
6. `git diff trading/paper_broker.py` sau khi khôi phục sabotage Task 3 — phải rỗng.
   (`trading/storage/db.py` sẽ có thay đổi — đúng, đó là chú thích của Task 4.)
7. `git status --short` + `git diff --stat`. File được phép xuất hiện: `.gitignore`,
   `scripts/.spike_all_symbols_classified.json` (mới thêm), `scripts/backfill_universe.py`,
   `scripts/confirm_real_order.py`, `scripts/spike_ssi_sdk_auth.py`,
   `scripts/spike_ssi_symbols_classify.py`,
   `scripts/spike_ssi_sdk_derivative_ohlc_stream.py`, `trading/storage/db.py`,
   `DEPLOYMENT.md`, `tests/test_backfill_universe.py`, `tests/test_confirm_real_order.py`,
   cộng `AGENTS.md` + `CLAUDE.md` (do `analyze` sinh). **File nào khác cũng là lỗi** — báo
   cáo, đừng tự dọn.
8. GitNexus: hai lần `analyze`, `gitnexus_impact`, `gitnexus_detect_changes` — hoặc nói
   thẳng phần nào không chạy được.
9. Danh sách phát hiện **ngoài phạm vi**, không sửa.

**Output thô, nguyên văn.** Đợt 10, 14 và 16 đều từng có mô tả trong báo cáo không khớp mã
thật (bảng bịa, sai tên symbol) dù code đúng. Tôi sẽ chạy lại tất cả và đối chiếu.

---

## 6. Tiêu chí "xong"

- [ ] `npx gitnexus analyze` chạy trước và sau.
- [ ] `.spike_all_symbols_classified.json` nằm trong git; `.spike_all_symbols.json` **vẫn**
      bị loại.
- [ ] Thông báo lỗi của `backfill_universe.py` nêu đúng lệnh sinh lại file.
- [ ] `DEPLOYMENT.md` mô tả đủ chuỗi nạp `symbol_universe`.
- [ ] `git check-ignore -v .gitnexus/lbug` trỏ về `.gitignore`.
- [ ] `FEE_RATE_ESTIMATE` lấy từ `paper_broker.FEE_RATE`, sabotage chứng minh có răng.
- [ ] Bốn file đã có nhãn "không phải spike vứt đi".
- [ ] Toàn bộ suite 0 failed; ruff sạch; `git diff trading/paper_broker.py` rỗng.
- [ ] Hai literal `0.0025` trong `tests/test_confirm_real_order.py` **giữ nguyên**.
- [ ] Không xoá file nào.
- [ ] Chưa commit, chưa push.

---

## 7. Việc của chủ dự án (không giao agent)

Ngoài bốn việc đã treo từ đợt 15 (rebuild image, tạo task `trading-engine-cam`, Docker tự
khởi động, quan sát token sáng mai), lần quét này thêm:

| # | Việc | Ghi chú |
|---|---|---|
| O-5 | `docker image rm` 10 image `autotrading-*` từ 07/06/2026 | dọn đĩa, không ảnh hưởng gì đang chạy |
| O-6 | Quyết định có xoá 3 file spike ở mục 2.4 không | tôi nghiêng về **không** — giá trị gần bằng 0, rủi ro nhỏ nhưng khác 0 |
