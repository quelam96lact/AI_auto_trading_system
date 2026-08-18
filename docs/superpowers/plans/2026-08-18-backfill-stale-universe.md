# Plan (Hermes): backfill vũ trụ ghi nhận thành công cho dữ liệu nó không có

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:test-driven-development,
> task-by-task, checkbox tracking. Chạy `gitnexus_impact` trên
> `set_backfill_progress` và `backfill_one` TRƯỚC khi sửa (đều có caller thật),
> `gitnexus_detect_changes` trước khi báo cáo. **KHÔNG commit, KHÔNG push.**

## Vì sao

Tính năng kiểm đầy đủ (merge hôm nay, `4272730`) phát hiện: **`bars_daily` toàn
vũ trụ dừng ở 2026-08-07**, trong khi hôm nay là 2026-08-18. Sau 07/08 chỉ còn
**10 mã** có dữ liệu — đúng `config.symbols` cộng danh mục đang nắm, tức phần do
collector real-time ghi, không phải do backfill.

Mọi backtest chạy hôm nay dùng dữ liệu cũ 11 ngày. Đây là thứ đang âm thầm làm
sai lệch mọi phép đo dùng để quyết định go-live.

Đào tiếp thấy **hai vấn đề riêng biệt**, đừng gộp:

### Vấn đề 1 — progress ghi ngày YÊU CẦU, không phải ngày CÓ THẬT (bug)

`scripts/backfill_universe.py:91`:

```python
bars = await client.daily_ohlc(symbol, frm, to)
storage.write_daily(bars)
storage.set_backfill_progress(symbol, timeframe, to, "ok")   # <-- `to`
```

Ghi `to` bất kể `bars` chứa gì — **kể cả khi `bars` rỗng**. Rồi dòng 78:

```python
if prog["status"] == "ok" and prog["last_done_date"] >= to:
    return symbol, "skip", ""
```

Lần chạy sau với `to` không lớn hơn sẽ **bỏ qua mã đó hoàn toàn**. Lỗ hổng tự
bịt miệng: hệ thống ghi nhận thành công cho dữ liệu nó không có, rồi từ chối thử
lại. Bằng chứng thực tế trong DB hiện nay:

```
backfill_progress:  status=ok, last_done_date = 2026-08-10  (1594 mã, 1d)
bars_daily:         không mã vũ trụ nào có bar sau 2026-08-07
```

Progress nói xong tới 10/08. Dữ liệu nói dừng ở 07/08.

### Vấn đề 2 — không ai chạy backfill vũ trụ (thiếu vận hành, không phải bug)

`grep backfill DEPLOYMENT.md` → **không dòng nào**. `trading/collector/main.py`
không hề gọi backfill vũ trụ. `scripts/backfill_universe.py` là script **chạy
tay**. Dữ liệu cũ dần là hệ quả tất yếu, không phải sự cố.

## Nguyên tắc chỉ đạo (không thương lượng)

**Không bao giờ ghi nhận độ phủ mà mình không có.** Mọi cách sửa phải giữ được
tính chất: nếu dữ liệu tới ngày X không thực sự nằm trong DB thì progress không
được nói là đã xong tới X.

## Ngoài phạm vi (đừng làm)

- Không sửa `trading/collector/` (luồng real-time) — vấn đề nằm ở backfill.
- Không tự chạy backfill toàn vũ trụ để "vá luôn cho xong". Sửa code + kiểm
  chứng trên phạm vi nhỏ trước; chạy vá toàn bộ là quyết định của chủ dự án
  (tốn hàng nghìn lượt gọi API SSI).
- Không dựng lịch nghỉ lễ.

## Global constraints

- **Chỉ được sửa/thêm:** `scripts/backfill_universe.py`,
  `tests/test_backfill_universe.py` (tạo mới nếu chưa có),
  `trading/storage/db.py` (chỉ nếu thật sự cần, và chỉ THÊM),
  `DEPLOYMENT.md` (thêm mục lịch chạy).
- **KHÔNG đụng:** `trading/collector/`, `scripts/heartbeat_check.py`,
  `trading/real_orders.py`, `scripts/confirm_real_order.py`, `config/config.yaml`,
  `tests/conftest.py`, `trading/data_quality.py` (Antigravity đang làm việc khác
  trên file đó — chạm vào là hai luồng giẫm nhau).
- **KHÔNG bật `real_trading_enabled`.**
- Postgres đang phục vụ collector + engine chạy thật. Điều tra là READ-ONLY.
  Test dùng `trading_test` như `conftest.py` ép.
- Gọi API SSI: chỉ trong phạm vi nhỏ để kiểm chứng (vài mã), **không** quét toàn
  vũ trụ. Không xác thực OTP mới, không tạo credential mới.
- `scripts/` nằm trong phạm vi lint và đang **sạch 0 lỗi** — giữ nguyên.

---

## Các bước

### Task 1 — đo trước khi sửa: API trả gì cho một mã ít thanh khoản

Câu hỏi quyết định cách sửa: khi một mã **không có giao dịch** trong khoảng
`[frm, to]`, API trả mảng rỗng hay lỗi?

Chuyện này quan trọng vì nếu "rỗng" là hợp lệ và phổ biến, thì cách sửa ngây thơ
("chỉ ghi progress khi `bars` không rỗng") sẽ khiến hàng trăm mã bị fetch lại ở
**mọi lần chạy**, mãi mãi. Phải biết cái giá đó trước khi chọn.

Việc: gọi thử **vài mã** (dưới 10) — lấy mã cực ít thanh khoản từ báo cáo
`scripts/data_completeness_report.csv` (ví dụ `SDC`, `MCC`, `QST` —
`avg_value_20d` chỉ 1-11 triệu VND) trên một khoảng ngày mà chúng chắc chắn
không giao dịch. Dán response thật.

→ **Kiểm chứng:** dán output thật cho từng mã: rỗng, lỗi, hay có bar. Kèm số
lượng mã trong `symbol_universe` có `avg_value_20d` dưới 100 triệu (ước lượng
quy mô mã sẽ bị fetch lại mỗi lần).

### Task 2 — sửa: progress phản ánh độ phủ THẬT

Dựa trên kết quả Task 1, sửa `backfill_one` sao cho `last_done_date` phản ánh dữ
liệu thực sự có, không phải ngày yêu cầu.

**Hướng tôi khuyến nghị** (phản biện nếu Task 1 cho thấy nó sai): ghi
`last_done_date` = ngày của bar cuối cùng thực sự nhận được; nếu không nhận được
bar nào thì **không tiến** `last_done_date`.

**Nhưng** nếu Task 1 cho thấy "rỗng" là phổ biến ở mã ít thanh khoản, cách trên
làm chúng bị fetch lại vĩnh viễn. Khi đó đề xuất cách khác **và nói rõ đánh đổi**
— ví dụ tách biệt "đã hỏi tới ngày X" và "có dữ liệu tới ngày Y" thành hai cột.
Đừng tự chọn trong im lặng; nêu phương án kèm số liệu rồi làm.

→ **Kiểm chứng (TDD, đỏ trước):** test tối thiểu phải phủ:
- API trả bar tới ngày X < `to` → progress **không** được ghi `to`
- API trả **mảng rỗng** → progress **không** được tiến lên
- Lần chạy kế tiếp **không** `skip` mã chưa thực sự đủ dữ liệu (đây là test quan
  trọng nhất — nó bắt đúng cơ chế tự bịt miệng)
- Trường hợp bình thường (bar về đủ tới `to`) vẫn ghi `to` và vẫn `skip` lần sau

Sau khi xanh, **tự phá bản sửa** để chứng minh test bắt được. Sabotage phải nhắm
vào **nguyên tắc chỉ đạo** ở trên (ghi nhận độ phủ không có), không phải vào
dòng bạn vừa viết. Dán cả hai output đỏ.

### Task 3 — làm sạch progress đang nói dối

1594 dòng `1d` hiện ghi `last_done_date = 2026-08-10` trong khi dữ liệu dừng ở
07/08. Sau khi sửa code, những dòng đó vẫn khiến mọi lần chạy sau `skip`.

Việc: viết cách sửa lại các dòng progress sai cho khớp thực tế. **Bảng
`backfill_progress` là bảng trạng thái của backfill, không phải dữ liệu thị
trường** — được phép ghi, nhưng:

- Phải là script/lệnh **riêng, chạy có chủ đích**, không phải side effect lúc
  import hay lúc chạy backfill thường.
- Phải in ra **sẽ sửa bao nhiêu dòng, từ giá trị nào sang giá trị nào** trước
  khi ghi, và có chế độ chỉ-xem-không-ghi.
- **KHÔNG đụng** `bars`, `bars_daily`, hay bất kỳ bảng dữ liệu thị trường nào.

→ **Kiểm chứng:** chạy chế độ chỉ-xem trên DB thật, dán output (số dòng, giá trị
cũ → mới). **Đừng ghi thật** — đó là quyết định của chủ dự án, tôi sẽ hỏi.

### Task 4 — lên lịch chạy

Thêm mục vào `DEPLOYMENT.md` theo đúng khuôn mục cron hiện có (§9, dòng ~203,
xem mục của `heartbeat_check.py` làm mẫu). Chạy **sau giờ đóng cửa**, ngày trong
tuần.

Nêu rõ trong mục đó: lần chạy đầu sau thời gian dài không chạy sẽ nặng (nhiều
ngày × ~1.594 mã), và cách chạy giới hạn phạm vi để không bị SSI rate-limit.

→ **Kiểm chứng:** dán mục đã thêm. **Không tự cài cron lên máy.**

---

## Kiểm chứng cuối

```
uv run ruff check trading tests scripts      # All checks passed!
uv run pytest -m "not integration" -q        # 300 + đúng số test bạn thêm
uv run pytest -m "integration" -q            # 84 + đúng số test bạn thêm
```
(integration cần `TEST_DB_DSN` trỏ `trading_test` + `TEST_NATS_URL` cổng 4223)

Báo cáo: dán output THẬT nguyên văn. Việc nào không làm được thì nói rõ vì sao —
**đừng đoán bừa cho đủ**. Tách bạch "đã kiểm chứng" và "vẫn là suy luận", như
bạn đã làm tốt ở đợt CI.
