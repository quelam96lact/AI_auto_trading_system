# Plan: kiểm `bars_daily` đã đầy đủ chưa — mã nào thiếu phiên nào

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development,
> task-by-task, checkbox tracking. Chạy `gitnexus_context` trước khi sửa
> `Storage` (có caller thật), `gitnexus_detect_changes` trước khi báo cáo xong.
> **KHÔNG commit, KHÔNG push** — báo cáo lại cho Claude (planner) audit.

## Vì sao

Mọi backtest hiện nay chạy trên `bars_daily`. Chưa ai trả lời được câu
"dữ liệu có đủ để TIN kết quả không". Đã có 4 script kiểm **chất lượng**
(`check_price_adjustment.py` — đã back-adjust chưa; `check_refprice_reset.py`;
`classify_overnight_gaps.py` — 837 bước nhảy >25%; `heartbeat_check.py` 2A —
bar *ngừng* về). **Không cái nào kiểm tính đầy đủ**: mã X có thiếu phiên nào
không, thiếu bao nhiêu.

Chủ dự án chọn phạm vi: **chỉ `bars_daily`**, và làm **cả hai lớp** — CLI chạy
tay (kiểm một lần trước go-live) + job định kỳ (bắt collector bỏ sót).

## Giả định đã chốt — nêu rõ để phản biện nếu sai

**1. "Phiên đáng lẽ phải có" suy từ chính dữ liệu, KHÔNG dựng lịch nghỉ lễ.**

`config/config.yaml:6` có `holidays: ['2026-09-02']` — đúng một ngày. Không có
Tết, 30/4, 1/5, Giỗ Tổ. Với dữ liệu nhiều năm thì danh sách này vô dụng.
`scripts/heartbeat_check.py:89` cũng đã ghi rõ *"KHÔNG tự dựng lịch nghỉ lễ
(chưa được giao)"*.

Thay bằng **đồng thuận**: một ngày là phiên giao dịch nếu **đủ nhiều mã trong vũ
trụ có bar ngày đó**. Ngày nghỉ lễ → gần như không mã nào có bar → tự động không
tính là phiên. Tự hiệu chỉnh, không phải bảo trì hằng năm.

**Ngưỡng đồng thuận phải ĐO, không được đoán** — xem Task 1.

**2. Chỉ tính thiếu TRONG đời sống của mã.** Mã niêm yết 2020 không bị coi là
"thiếu" các phiên 2016-2019. Chặn bằng bar đầu tiên và bar cuối cùng của chính mã đó.

**3. Vắng mặt ở ĐUÔI là chuyện khác với lỗ hổng ở GIỮA.** Mã hủy niêm yết/đình
chỉ dài hạn sẽ thiếu toàn bộ phần đuôi — đó không phải lỗi thu thập. Hai loại
này phải báo riêng, không gộp một số.

## Ngoài phạm vi (đừng làm)

- Bar 5 phút (`bars`). Thiếu khung 5m ở mã ít thanh khoản là **bình thường**
  (không có lệnh khớp), cần định nghĩa khác hẳn — plan riêng nếu muốn.
- **Tự vá dữ liệu thiếu.** Plan này chỉ ĐO và BÁO. Không gọi backfill, không
  `INSERT`/`UPDATE`/`DELETE` bất cứ thứ gì.
- Sửa `scripts/heartbeat_check.py` (dead-man's switch, hợp đồng exit code riêng).

## Global constraints

- **Chỉ được sửa/thêm:** `trading/data_quality.py` (mới),
  `tests/test_data_quality.py` (mới), `scripts/check_data_completeness.py` (mới),
  `scripts/daily_data_check.py` (mới), `trading/storage/db.py` (chỉ THÊM hàm đọc,
  không sửa hàm sẵn có), `DEPLOYMENT.md` (chỉ thêm mục cron mới).
- **TUYỆT ĐỐI READ-ONLY với Postgres.** Instance này đang phục vụ collector +
  engine chạy thật.
- Dùng `resolve_dsn()` trong `scripts/_db_common.py` (8 script đã dùng), đừng tự
  giải DSN.
- `scripts/` **nằm trong phạm vi lint** và đang **sạch 0 lỗi** — giữ nguyên.
  Đừng chạy `ruff check --fix` theo wildcard.

---

## BẪY KỸ THUẬT — đọc trước khi viết dòng SQL đầu tiên

**Bẫy 1 — `ts::date` phụ thuộc timezone của session Postgres.** Repo đã vấp
đúng chỗ này: `Storage.read_real_daily_pnl` (`db.py:754`) ghi rõ cast trực tiếp
"phụ thuộc timezone của session/server Postgres (thường mặc định UTC, không cấu
hình rõ ràng ở đâu trong dự án), có thể quy sai ngày cho các dòng gần ranh giới
nửa đêm".

**Bắt buộc dùng `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`** ở MỌI truy vấn
của plan này. Cast trần là sai.

**Bẫy 2 — bar rác đã "có dòng" nhưng vô giá trị.** `bars_daily` có dòng
`OHLC <= 0` (971 mã dính, `trading/backtest.py::_is_dirty` là định nghĩa chuẩn —
dùng lại, đừng viết định nghĩa thứ hai). Một ngày có bar rác **không phải là
thiếu**, nhưng cũng **không phải là đủ**. Phải đếm thành hạng mục thứ ba riêng.

**Bẫy 3 — phải kiểm giả định "một mã một ngày một dòng" trước khi làm số học.**
Khóa chính là `(symbol, ts)`, không phải `(symbol, ngày)`. Nếu tồn tại hai `ts`
khác giờ trong cùng một ngày thì phép trừ ở Task 2 sai âm thầm. **Kiểm bằng
truy vấn, dán kết quả** — nếu có vi phạm thì DỪNG và báo cáo, đừng tự chọn cách xử lý.

---

## Các bước

### Task 1 — đo ngưỡng đồng thuận, đừng đoán

Truy vấn (read-only, kết quả nhỏ ~2.500 dòng):

```sql
SELECT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS d,
       count(DISTINCT symbol) AS n
FROM bars_daily GROUP BY 1 ORDER BY 1;
```

Kỳ vọng phân bố **hai cụm tách bạch**: ngày giao dịch có hàng nghìn mã, ngày
nghỉ có ~0. Việc: dán histogram/phân bố của `n`, chỉ ra khoảng trống giữa hai
cụm, rồi **chọn ngưỡng nằm trong khoảng trống đó** và nói rõ vì sao.

**Nếu hai cụm KHÔNG tách bạch** (có nhiều ngày ở giữa) thì giả định đồng thuận
sai → **DỪNG, báo cáo**, đừng tự chế biến thể. Đó là phát hiện có giá trị.

→ **Kiểm chứng:** dán số liệu phân bố thật + ngưỡng đã chọn + lý do.

### Task 2 — lõi thuần, không I/O

Thêm `trading/data_quality.py`. Hàm thuần (nhận dữ liệu, trả kết quả — **không**
chạm DB, để test được không cần Postgres):

- suy tập phiên từ `{ngày: số mã}` + ngưỡng
- với mỗi mã, cho biết: số phiên thiếu **ở giữa** đời sống, số phiên thiếu **ở
  đuôi**, số ngày **có bar rác**

Tên hàm/chữ ký tự chọn theo style sẵn có của repo.

→ **Kiểm chứng (TDD, đỏ trước):** test tối thiểu phải phủ — mã niêm yết muộn
không bị tính thiếu phần trước khi niêm yết; mã hủy niêm yết ra "thiếu đuôi"
chứ không phải "thiếu giữa"; lỗ hổng kẹp giữa hai bar có mặt ra "thiếu giữa";
ngày nghỉ lễ (ít mã) không bị tính là phiên; bar rác vào đúng hạng mục thứ ba.
Sau khi xanh, **tự phá bản sửa để chứng minh test bắt được** — dán cả hai output đỏ.

### Task 3 — hàm đọc trong Storage

Thêm vào `trading/storage/db.py` (đặt cạnh các `read_*`, theo style của chúng)
các hàm đọc **tổng hợp bằng SQL**, không kéo 2,97 triệu dòng về RAM:

- `{ngày: số mã}` (truy vấn Task 1)
- theo mã: ngày đầu, ngày cuối, số ngày có bar, số ngày có bar rác

Có hai con số đó thì **số phiên thiếu = số phiên kỳ vọng trong đời sống − số
ngày có bar**, không cần liệt kê từng ngày. **Chỉ truy vấn chi tiết từng ngày
cho những mã thật sự có lỗ hổng** — đừng quét chi tiết toàn vũ trụ.

→ **Kiểm chứng:** test integration (marker `integration`, dùng `trading_test`
như `conftest.py` ép) dựng vài mã giả với lỗ hổng đã biết, khẳng định hàm trả
đúng. Dán output.

### Task 4 — CLI chạy tay

`scripts/check_data_completeness.py`, dùng `resolve_dsn()`. In tóm tắt ra màn
hình + ghi CSV chi tiết (file, **không phải bảng DB** — giống
`classify_overnight_gaps.py` ghi `research_gap_causes.csv`).

Tối thiểu có cờ giới hạn phạm vi (khoảng ngày, số mã) để chạy thử nhanh trước
khi chạy toàn bộ.

→ **Kiểm chứng:** chạy thật trên DB, dán output thật: bao nhiêu mã đủ, bao nhiêu
mã thiếu giữa, bao nhiêu mã thiếu đuôi, top mã thiếu nhiều nhất. **Đây là câu trả
lời cho câu hỏi gốc của chủ dự án** — dán nguyên văn, đừng tóm tắt.

### Task 5 — job định kỳ

`scripts/daily_data_check.py`: sau phiên, kiểm các mã `is_active` trong
`symbol_universe` có bar của phiên gần nhất chưa. Thiếu → `send_telegram`
(`trading/telegram.py`, giống `heartbeat_check.py:31`).

**Hợp đồng exit code theo đúng `heartbeat_check.py`:** `0` = ổn, `1` = đã gửi
cảnh báo, `2` = sai cấu hình.

**Phân định rõ với heartbeat 2A, tránh cảnh báo chồng:** 2A bắt "bar ngừng về"
(cả feed chết). Việc này bắt "feed sống nhưng SÓT mã". Nếu **không mã nào** có
bar thì đó là chuyện của 2A → job này phải im (một sự cố không được bắn hai
kiểu cảnh báo từ hai chỗ).

Thêm dòng cron vào `DEPLOYMENT.md` theo đúng khuôn mục hiện có (§9, dòng 203).
Chạy **sau 15:00** giờ VN, ngày trong tuần.

→ **Kiểm chứng:** test cho cả ba nhánh exit code + nhánh im-lặng-khi-cả-feed-chết.
Dán output.

---

## Kiểm chứng cuối

```
uv run ruff check trading tests scripts      # phải: All checks passed!
uv run pytest -m "not integration" -q        # 287 + đúng số test bạn thêm
```

Cộng output CLI thật ở Task 4.

Báo cáo: dán output THẬT nguyên văn, đừng tóm tắt thành "pass". Việc nào không
làm được thì nói rõ vì sao — **đừng đoán bừa cho đủ**. Phát hiện vấn đề ngoài
phạm vi thì **báo cáo, đừng tự sửa**.
