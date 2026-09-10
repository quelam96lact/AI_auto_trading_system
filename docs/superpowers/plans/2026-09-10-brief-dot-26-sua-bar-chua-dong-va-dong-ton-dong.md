# Brief đợt 26 — Sửa lỗi bar chưa đóng, và đóng nốt tồn đọng trước go-live

Ngày giao: 10/09/2026, 08:50.
Base: `e47c2f0` (main, cây sạch).
Người giao: Claude (planner/auditor).

**Brief này THAY THẾ brief đợt 25** (`2026-09-09-brief-dot-25-dong-cac-ton-dong-sau-phien.md`),
chưa từng được thực thi. Bốn task của đợt 25 vẫn còn nguyên giá trị và được giữ lại ở đây
thành Task 4–7, nhưng thứ tự ưu tiên đã đổi vì phát hiện mới. **Đọc brief 25 để lấy chi tiết
Task 4–7; brief này là bản điều phối và chứa toàn văn Task 1–3.**

---

## 0. Đọc trước tiên — bối cảnh đã đổi so với hôm qua

Sáng nay tôi đã **xác nhận dứt điểm** phát hiện nghiêm trọng của đợt 24 bằng message thô đọc
lại từ JetStream. Bằng chứng đầy đủ:
`docs/superpowers/research/2026-09-10-xac-nhan-bar-chua-dong-bang-message-tho.md`.

Tóm tắt điều agent cần biết:

- Phiên 09/09: **860 message NATS ↔ chỉ 120 khung 5 phút duy nhất** (7,17 message/bar).
  Một khung bị phát tới 30 lần.
- Payload **thay đổi** giữa các lần phát: `volume` tăng đơn điệu (200 → 123.800), `high` nới
  rộng, `low` co lại, `open` bất biến. Đây là **snapshot nến đang chạy**, không phải phát lại.
- Engine chạy toàn bộ pipeline chiến lược ~7 lần mỗi cây nến, trên OHLC **chưa hoàn chỉnh**.

> **Không cần điều tra lại. Không cần bắt dữ liệu trong phiên. Việc của đợt 26 là SỬA.**

Hai điều **đã kiểm chứng là KHÔNG hỏng**, đừng đụng vào và đừng "sửa cho chắc":

1. Bảng `bars` trong DB **đúng**. `ON CONFLICT ... DO UPDATE` luôn giữ snapshot cuối cùng của
   khung = giá trị đóng đúng. Mọi backtest và cổng cứng VN vẫn hợp lệ.
2. `num_pending` / `num_redelivered` luôn bằng 0 — JetStream và consumer engine **khoẻ**.
   Lỗi nằm ở chỗ collector phát cái gì, không phải ở đường truyền.

---

## 1. Thứ tự thực hiện và cổng thời gian

Hôm nay **10/09 là ngày giao dịch**, phiên 09:00–15:00.

| Task | Việc | Khi nào |
|---|---|---|
| 1 | `BarLatch` — chỉ phát khung ĐÃ ĐÓNG ra NATS | làm ngay, trong phiên (chỉ sửa code + test) |
| 2 | Rào chắn phía engine: bỏ qua bar `ts` không tiến lên | sau Task 1 |
| 3 | Kiểm chứng lại bằng message thô của phiên hôm nay | **sau 15:05** |
| 4 | `_buy_and_hold` hỗ trợ khối lượng phân số | song song, bất cứ lúc nào |
| 5 | Chuông 2C — giám sát engine tiêu thụ bar | song song, bất cứ lúc nào |
| 6 | Điều tra HII câm (chỉ đọc, chỉ báo cáo) | song song, bất cứ lúc nào |
| 7 | Triển khai image mới | **sau 15:05**, và chỉ sau khi Task 1–3 xong |

> **TUYỆT ĐỐI KHÔNG `docker compose build` / `up` / `restart` trước 15:05.** Dựng lại
> collector giữa phiên làm mất bar của khoảng thời gian gián đoạn — và hôm nay là ngày duy
> nhất còn lại để có một phiên "trước khi sửa" sạch làm mốc so sánh cho Task 3.

Task 1, 2, 4, 5, 6 chỉ sửa file nguồn và chạy test trên DB `trading_test` — **không** chạm hệ
thống đang chạy. Làm thoải mái trong phiên.

---

## 2. Ràng buộc

- `real_trading_enabled` giữ `false`. Không đổi.
- **Không gọi SSI, không gọi BingX.** Backtest chỉ đọc DB.
- Không in secret. `.env` không sửa, không commit, không mở.
- `config/config.yaml` **không sửa** (kể cả `holidays`).
- Không `TRUNCATE` / `DROP` / xoá dòng trên DB `trading`. Task 3 và 6 chỉ `SELECT`.
- **Không `delete`, `purge`, `add`, `update` bất kỳ stream hay consumer NATS nào.** Task 3
  chỉ được dùng `js.get_msg()` và `js.stream_info()` — hai lệnh đọc. (Sự cố 13/08: suite test
  đã xoá durable consumer của engine thật và purge stream `BARS`.)
- **Không sửa** `PaperBroker`, `trading/risk.py`, `trading/strategies/*`,
  `derivative_backtest`, `pattern_backtest`, `scripts/heartbeat_check.py` (lý do ở Task 5).
- **Không sửa** `trading/collector/aggregator.py` — xem §3.2, nó không phải công cụ đúng cho
  việc này, nhưng cũng không được xoá (có test riêng, và vẫn là đường dùng cho dữ liệu tick).
- **Không xoá file nào. Không commit. Không push.** Tôi audit rồi mới commit.
- Phát hiện ngoài phạm vi: **báo cáo, không tự sửa**.
- **Mọi `git diff` trong báo cáo phải copy từ lệnh `git diff`**, không gõ lại. Tôi đối chiếu
  từng dòng ngữ cảnh với file thật. Đợt 22 đã có một `git diff` bịa — mọi dòng ngữ cảnh đều
  sai so với file thật.
- **Phép đo phải là bước CUỐI CÙNG.** Đo xong rồi sửa code thì số đo vô giá trị (bài học đợt
  22: báo cáo −12,24 nhưng chạy lại ra −15,58 vì đo trước, sửa sau).

**GitNexus:** `npx gitnexus analyze` trước và sau; `gitnexus_impact` cho
`make_stream_message_handler`, `persist_bars`, `_buy_and_hold` trước khi sửa;
`gitnexus_detect_changes()` khi xong. MCP `gitnexus` phiên gần đây hay timeout — **không kết
nối được thì ghi rõ trong báo cáo**, đừng lặng lẽ bỏ qua rồi sửa code.

---

## Task 1 — `BarLatch`: chỉ phát khung ĐÃ ĐÓNG ra NATS

### 1.1. Nguyên nhân, đã xác minh

`trading/collector/main.py:101-116`:

```python
    def on_stream_message(msg):
        try:
            bar = parse_interval_message(msg)
        except Exception as e:
            ...
            return
        if bar is not None:
            wd.beat()
            task = asyncio.create_task(persist_bars(storage, pub, [bar]))
```

Mỗi snapshot SSI gửi tới → một `persist_bars` → một `pub.publish(b)`. Không có bước nào hỏi
"khung này đóng chưa".

### 1.2. Vì sao KHÔNG dùng lại `BarAggregator`

Phản xạ tự nhiên là "đã có `BarAggregator`, cắm nó vào". **Sai, và tôi đã kiểm tra.**
`aggregator.py:28-44`, `add_tick` nhận `Tick` và **cộng dồn** volume:

```python
            cur.volume += t.volume
```

Snapshot của SSI mang volume **luỹ kế sẵn** trong khung (đo được: 200 → 6.200 → 20.000 →
123.800 trong cùng một khung). Cộng dồn tiếp sẽ thổi volume lên hàng chục lần. `BarAggregator`
là công cụ đúng cho **tick**, không phải cho **snapshot**. Giữ nguyên, không đụng.

### 1.3. Việc cần làm

Tạo file mới `trading/collector/latch.py` với một lớp `BarLatch`. Ngữ nghĩa:

- `offer(bar) -> Bar | None`: nhận một snapshot. Nếu snapshot thuộc **khung mới** so với
  khung đang mở của mã đó → khung cũ là **CHỐT**, trả về nó. Ngược lại trả `None`.
- Snapshot mới của **cùng** khung **ghi đè** snapshot cũ (nó mới hơn, đầy đủ hơn).
- Snapshot **đến muộn** (`bar.ts` < khung đang mở) → **bỏ qua, không ghi đè, không chốt**,
  và gọi `alert("WARN", ...)` vì đây là điều bất thường cần nhìn thấy.
- `flush_due(now) -> list[Bar]`: chốt mọi khung đang mở đã quá hạn an toàn.
- `flush_all() -> list[Bar]`: chốt tất cả, dùng khi shutdown.

**Vì sao bắt buộc phải có `flush_due`:** khung cuối phiên (14:45) **không bao giờ có snapshot
kế tiếp** để kích hoạt việc chốt. Không có `flush_due` thì mỗi ngày mất đúng cây nến cuối
cùng — đổi một lỗi lấy một lỗi khác. Quy tắc quá hạn: một khung `ts` là quá hạn khi
`now >= ts + interval + grace`, với `grace = 60` giây. Đặt `interval` và `grace` thành tham
số của `__init__`, không hằng số rải rác.

### 1.4. Đấu dây vào `on_stream_message`

Tách rõ hai việc mà hiện tại `persist_bars` đang gộp:

- **Ghi DB: mỗi snapshot đều ghi.** Giữ nguyên hành vi này. DB dùng upsert nên snapshot sau
  ghi đè snapshot trước, giá trị cuối vẫn đúng, và Grafana vẫn thấy giá nhúc nhích trong
  khung. Không có lý do gì để làm dashboard chết đi.
- **Publish NATS: chỉ khi khung đóng.** Đây là toàn bộ nội dung của bản sửa.

Giữ `persist_bars` cho bar đã chốt (ghi + publish) và thêm đường ghi-DB-only cho snapshot.
Bar đã chốt sẽ bị ghi DB hai lần với **cùng một giá trị** — upsert nên vô hại, đổi lại code
đơn giản hơn hẳn; đừng tối ưu chỗ này.

Gọi `flush_due` từ `housekeeping_tick` trong `trading/collector/main.py` (hàm này đã chạy
định kỳ sẵn — **một phụ thuộc mới là một cách mới để chuông chết câm**, bài học `51ff6de`).
Gọi `flush_all` ở nhánh `finally` của `main()`, cạnh chỗ chờ `persist_tasks` (dòng 261-270).

Giữ nguyên style code hiện có. Không "tiện thể" refactor `persist_bars`, không dọn code xung
quanh, không đổi tên gì.

### 1.5. Cập nhật docstring `parse_interval_message` — bắt buộc, không phải tuỳ chọn

`trading/collector/parser.py:71-77` hiện ghi:

```python
    """Map ssi-sdk IntervalMessage to Bar.

    UNCONFIRMED WITH LIVE STREAM DATA: interval_time/trading_time string format.
    This assumes the same "YYYY/MM/DD HH:mm:ss" format verified for REST OHLC.
    If SSI stream uses a different format, return None so one bad message does
    not crash the collector; Phase 4 should verify this with a real session.
    """
```

Docstring này giờ **sai theo hướng nguy hiểm**. Sửa lại cho đúng hai điều đã biết chắc:

1. Định dạng `"%Y/%m/%d %H:%M:%S"` **đã được xác nhận** với dữ liệu stream thật — 860/860
   message của phiên 09/09 parse thành công (báo cáo 10/09). Bỏ chữ "UNCONFIRMED" và bỏ câu
   "Phase 4 should verify".
2. **Ghi rõ điều quan trọng hơn:** một `IntervalMessage` là **snapshot của khung đang hình
   thành**, KHÔNG phải sự kiện đóng nến. SSI phát lại cùng một khung trung bình 7 lần (đo
   được, cao nhất 30 lần), `volume` là luỹ kế trong khung, `open` bất biến, `close` là giá
   tạm thời. Ai gọi hàm này mà publish thẳng ra là tái lập đúng lỗi vừa sửa — nói thẳng câu
   đó trong docstring và trỏ tới `BarLatch`.

**Chỉ sửa docstring. Không đổi một dòng logic nào** trong `parse_interval_message` — hàm này
đang chạy đúng. Đây là lý do duy nhất `parser.py` được phép xuất hiện trong `git diff`.

### 1.6. Kiểm chứng — tiêu chí thành công

Test mới trong `tests/test_collector_latch.py` (file mới) cho `BarLatch`:

1. Ba snapshot cùng khung → `offer` trả `None` cả ba lần.
2. Snapshot thứ tư sang khung mới → trả về bar của khung cũ, và **giá trị của nó bằng
   snapshot thứ ba** (snapshot cuối cùng), không phải snapshot đầu.
3. Snapshot đến muộn (`ts` nhỏ hơn khung đang mở) → trả `None`, khung đang mở **không đổi**.
4. `flush_due` trước hạn → rỗng; sau `ts + interval + grace` → trả đúng bar đó, và gọi lần
   hai trả rỗng (không chốt hai lần).
5. `flush_all` trả mọi khung đang mở của **nhiều mã** cùng lúc.

Test đấu dây trong `tests/test_collector_main.py` (file đã có, thêm test mới, **không sửa
test cũ**):

6. Bơm 3 snapshot khung A rồi 1 snapshot khung B qua `on_stream_message`, với `pub` giả:
   → `pub.publish` được gọi **đúng 1 lần**, với bar khung A mang giá trị của snapshot thứ 3;
   → `storage.write_bars` được gọi **4 lần** (mỗi snapshot một lần).

Đây là tiêu chí quan trọng nhất của cả brief. Nó tái hiện đúng lỗi thật rồi làm cho nó pass.

7. Toàn bộ suite: `docker compose --profile test up -d nats-test` rồi `uv run pytest -q` →
   **620 test cũ vẫn pass**, cộng các test mới. Báo cáo con số đầy đủ.
8. `uv run ruff check trading tests scripts` → sạch.
9. **Cổng cứng VN tái lập chính xác**: `-1.615.319.902 | 1.514 lệnh | 439 mã |
   BH 1.897.587.481.903`. Task 1 không đụng backtest nên phải khớp **từng chữ số**. Lệch một
   chữ số = bản sửa bị từ chối.

---

## Task 2 — Rào chắn phía engine

### 2.1. Vì sao cần, dù Task 1 đã sửa đúng chỗ

Task 1 sửa **nguồn phát**. Nhưng engine hiện **tin tuyệt đối** mọi bar nó nhận được. Nếu mai
kia SSI đổi hành vi, hoặc một đường ghi khác publish nhầm, engine lại âm thầm chạy chiến lược
trên dữ liệu rác — và không ai biết, đúng như 2 tháng vừa qua.

Đây là cùng một triết lý với ISO-1…ISO-5: **rào chắn, không phải niềm tin vào hiện trạng**.
Đợt 23 tôi đã bác lập luận "hiện không có test nào gọi SSI thật nên không cần chắn" — lập
luận đó dựa trên hiện trạng, không dựa trên rào chắn.

### 2.2. Việc cần làm

`trading/engine/main.py` đã có một lá chắn chống nạp trùng ở dòng 398-403, nhưng nó chỉ so
với `warmed_until` — mốc **đặt một lần lúc warm-up**, nên hai snapshot của cùng cây nến trong
phiên đều lọt qua.

Thêm một mốc **tiến theo thời gian chạy**: nhớ `ts` của bar gần nhất **đã xử lý** cho từng mã.
Bar mới có `ts` **không lớn hơn** mốc đó → `alert("WARN", ...)` kèm `symbol` và cả hai `ts`,
rồi `ack` và bỏ qua, **không** gọi `process_bar`.

Chỉ sửa `trading/engine/main.py`. **Không sửa** `trading/engine/logic.py`, không đổi chữ ký
`process_bar`.

Chạy `gitnexus_impact` trên vùng này trước khi sửa và báo cáo blast radius — đây là vòng lặp
chính của engine, rủi ro cao. **Nếu impact trả về HIGH/CRITICAL, dừng lại và báo cáo cho tôi
trước khi sửa.**

### 2.3. Kiểm chứng

1. Test mới: hai bar cùng `ts` cùng mã → `process_bar` được gọi **đúng 1 lần**, bar thứ hai
   vẫn được `ack`.
2. Test: bar `ts` lùi về quá khứ → bị bỏ qua, có `WARN`.
3. Test: hai mã khác nhau, cùng `ts` → **cả hai đều được xử lý** (mốc phải theo từng mã;
   đây là bẫy dễ mắc nhất khi viết lá chắn kiểu này).
4. Suite đầy đủ pass, ruff sạch, cổng cứng VN vẫn khớp từng chữ số.

---

## Task 3 — Kiểm chứng lại bằng message thô của phiên hôm nay (**sau 15:05**)

Đây là phép đo **trước khi sửa** trên một phiên độc lập, để chứng minh phát hiện không phải
hiện tượng riêng của ngày 09/09.

1. Đọc `stream_info("BARS")` lấy `first_seq` / `last_seq`.
2. Xác định dải seq của phiên hôm nay (10/09).
3. Dùng **`js.get_msg("BARS", seq=N)`** đọc từng message trong dải đó. **Chỉ lệnh này.**
   Không subscribe, không tạo consumer.
4. Đếm: tổng message, số `(symbol, ts)` duy nhất, tỷ lệ message/bar, phân bố số lần phát.
5. Chọn khung bị phát nhiều nhất, in bảng OHLCV theo `seq` như báo cáo ngày 10/09 đã làm.

**Tiêu chí:** tỷ lệ message/bar của phiên 10/09 phải **lớn hơn 1 rõ rệt** (dự kiến 5–9×), và
`volume` trong cùng khung phải tăng đơn điệu. Nếu tỷ lệ ra ≈ 1,0 thì **dừng lại, báo cáo
ngay** — nghĩa là kết luận của tôi có chỗ sai và Task 1 có thể đang sửa nhầm vấn đề.

Script đặt tại `scripts/replay_stream_check.py`, nhận `--from-seq` / `--to-seq`, có docstring
nói rõ **CHỈ ĐỌC**. Đây là công cụ chẩn đoán dùng lại được, nên vào `scripts/`, không phải
scratchpad.

**Không** chạy phép đo này trước 15:05 — phiên chưa xong thì dải seq chưa đủ.

---

## Task 4 — `_buy_and_hold` hỗ trợ khối lượng phân số

Nguyên văn Task 1 của brief đợt 25, giữ nguyên không đổi:
`docs/superpowers/plans/2026-09-09-brief-dot-25-dong-cac-ton-dong-sau-phien.md`, mục "Task 1".

Tóm tắt để agent không đọc nhầm: `trading/backtest.py:95` dùng `int(...)` nên với vốn 500
USDT và giá BTC ~100k, `qty` luôn bằng 0 → cột benchmark toàn `+0,00`, khiến bảng số crypto
của đợt 23 **không trả lời được câu hỏi quan trọng nhất**: chiến lược có thua mua-và-giữ
không. Sửa xong **chạy lại đủ 8 phép đo** của đợt 23.

Nhắc lại ràng buộc dễ vi phạm nhất: cổng cứng VN phải tái lập **chính xác**. `_buy_and_hold`
nằm trong đường chạy của cổng cứng — đây là chỗ dễ làm vỡ nhất trong cả brief. Chạy
`gitnexus_impact` trên `_buy_and_hold` trước khi sửa.

---

## Task 5 — Chuông 2C: giám sát engine tiêu thụ bar

Nguyên văn Task 2 của brief đợt 25. Nhắc lại hai điểm bắt buộc:

- Viết thành **script riêng** `scripts/engine_consumer_check.py`. **KHÔNG** nhét vào
  `scripts/heartbeat_check.py`. Bài học `51ff6de`: *một phụ thuộc mới là một cách mới để
  chuông chết câm*. Chuông báo cháy không được phụ thuộc vào chuông báo khói.
- Chỉ gọi `js.consumer_info()` — lệnh đọc. Không tạo, không sửa, không xoá consumer.

Đợt 24 đã chứng minh khoảng trống này có thật: `heartbeat` engine vẫn tươi trong khi không ai
giám sát việc engine có thực sự tiêu thụ bar hay không.

---

## Task 6 — Điều tra HII câm (chỉ đọc, chỉ báo cáo)

Nguyên văn Task 4 của brief đợt 25. **Chỉ `SELECT`, chỉ báo cáo, không sửa một dòng code
nào.** Đợt 22 xác nhận HII sinh 0 tín hiệu bull trên 3.287 bar dù cổng thanh khoản mở 43,1%.

Câu hỏi cần trả lời: điều kiện nào trong `octopus_pullback` không bao giờ thoả với phân bố
giá của HII. Trả lời bằng số liệu, **không** bằng phỏng đoán.

---

## Task 7 — Triển khai (**sau 15:05, và chỉ sau khi Task 1–3 xong**)

Nguyên văn Task 3 của brief đợt 25, cộng thêm: image mới lần này **chứa cả bản sửa Task 1 và
Task 2**, nên đây không còn là "triển khai cho hết drift" mà là **triển khai bản sửa lỗi
nghiêm trọng**.

Drift đo lúc 08:35 hôm nay vẫn còn:

```
[deploy-drift] collector: image CŨ hơn commit gần nhất chạm trading/ (5 giờ 7 phút)
[deploy-drift] engine: image CŨ hơn commit gần nhất chạm trading/ (5 giờ 7 phút)
exit=1
```

Sau khi `docker compose build collector engine && docker compose up -d --no-deps collector
engine`:

1. `uv run python scripts/deploy_drift_check.py` → **exit 0**.
2. `docker compose logs --tail=50 collector` và `engine` → không có `CRITICAL`, không có
   traceback.
3. Ghi lại `docker ps` và image ID mới.

Giữ nguyên `dot20-rollback-collector:pre` và `dot20-rollback-engine:pre` làm đường lùi.
**Không xoá.**

---

## 8. Báo cáo nghiệm thu — những gì tôi sẽ đối chiếu

Tôi chạy lại độc lập, không tin số dán vào. Cụ thể tôi sẽ tự làm:

- Chạy lại toàn bộ suite và ruff.
- Chạy lại cổng cứng VN, so **từng chữ số**.
- Đọc `git diff` thật và đối chiếu **từng dòng ngữ cảnh** với file trên đĩa.
- Tự chạy lại `scripts/replay_stream_check.py` trên dải seq của phiên 10/09.
- Thêm phép thử phá hoại của riêng tôi vào `BarLatch` — cụ thể là snapshot đến muộn, hai mã
  cùng `ts`, và khung cuối phiên không có snapshot kế tiếp.

Báo cáo cần có, theo thứ tự:

1. Kết quả `npx gitnexus analyze` trước/sau và `gitnexus_impact` cho từng symbol được sửa
   (hoặc ghi rõ MCP timeout nếu không kết nối được).
2. `git diff` **copy nguyên văn** cho từng file.
3. Danh sách file mới tạo.
4. Kết quả từng tiêu chí kiểm chứng của Task 1 và Task 2, ghi rõ pass/fail từng mục.
5. Số test pass/fail đầy đủ + output ruff.
6. Cổng cứng VN.
7. Bảng kết quả Task 3 (tỷ lệ message/bar phiên 10/09 + bảng OHLCV một khung).
8. Bảng 8 phép đo crypto sau khi sửa `_buy_and_hold`, có cột benchmark **khác 0**.
9. Kết luận Task 6 kèm số liệu.
10. Bằng chứng triển khai Task 7.
11. `git status --short` — để tôi biết chính xác những gì đã đụng vào.

**Không commit, không push.** Nộp báo cáo, tôi audit rồi commit.

---

## 9. Điều KHÔNG thuộc phạm vi đợt này

Những việc sau là **quyết định của chủ dự án**, không phải việc agent, và không được tự làm:

- Q-1: chiến lược chưa có edge đo được — có go-live hay không.
- Q-2: `real_order_account` cấu hình `0434221` nhưng tiền nằm ở `0434226`; danh sách `symbols`
  lệch nhau.
- Q-3: xác nhận lệnh + đối soát vị thế.
- Q-5: 10/13 ngày nghỉ lễ chưa khai báo trong `config.yaml`.
- Q-7: `risk_pct` cho mức phơi nhiễm 30x thật.
- Chuyển sang VPS, đặt scheduled task cho chuông 2C, bật Docker autostart.

Nếu agent thấy thứ gì trong nhóm này đang chặn công việc → **báo cáo, không tự quyết**.
