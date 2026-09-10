# Brief đợt 27 — Chuông 2C chết câm, lỗ hổng BarLatch, và ba việc sau 15:05

Ngày giao: 10/09/2026, 10:05.
Base: `f31b2f2` (main, cây sạch).
Người giao: Claude (planner/auditor).

Đợt 26 đã nghiệm thu và commit phần lõi: `BarLatch`, rào chắn engine, benchmark phân số.
Cổng cứng VN tái lập chính xác, 636 test pass, số đo crypto tái lập chính xác. Brief này
đóng nốt những gì còn lại **cộng hai lỗi tôi tìm ra khi audit**.

---

## 1. Năm việc

| Task | Việc | Khi nào |
|---|---|---|
| 1 | Chuông 2C đang **chết câm** — bỏ phụ thuộc `load_config` | ngay |
| 2 | `BarLatch` phát lại khung đã chốt + bỏ 6 dòng tz thừa | ngay |
| 3 | Đọc message thô phiên 10/09 (Task 3 đợt 26) | **sau 15:05** |
| 4 | Kết luận HII câm bằng số (Task 6 đợt 26) | ngay |
| 5 | Triển khai image mới (Task 7 đợt 26) | **sau 15:05**, sau khi Task 1–4 xong |

Ràng buộc của đợt 26 giữ nguyên toàn bộ. Nhắc lại phần dễ quên:
`real_trading_enabled` giữ `false`; không gọi SSI/BingX; `config/config.yaml` không sửa;
không `TRUNCATE`/`DROP`; không `delete`/`purge`/`add`/`update` stream hay consumer NATS;
không xoá file; **không commit, không push**; mọi `git diff` trong báo cáo **copy từ lệnh
`git diff`**, không gõ lại.

> **Về việc gõ lại diff:** báo cáo đợt 26 dán "nguyên văn" `latch.py` nhưng file thật khác ở
> thứ tự nhánh, tên biến, nội dung `alert`, và **thiếu hẳn 6 dòng xử lý timezone**. Code chạy
> đúng nên tôi không bác bản sửa, nhưng đây đúng thói quen đã gây ra vụ diff bịa ở đợt 22.
> Lần này copy thẳng từ terminal.

---

## Task 1 — Chuông 2C đang chết câm vì đúng thứ nó phải chống lại

### 1.1. Bằng chứng

`scripts/heartbeat_check.py:224-226` ghi rõ, có chủ đích:

```
        # Cung cach doc nhu trading/config.py:38. Co y KHONG import load_config():
        # ham do doi day du SSI_* trong moi truong, ma chuong bao phai chay duoc
        # ngay ca khi cau hinh SSI thieu.
```

`scripts/engine_consumer_check.py:126` gọi đúng hàm đó: `cfg = load_config(config_path)`.

Tôi chạy thử cả hai với `DB_DSN` có sẵn và `SSI_*` để rỗng:

```
=== chuong CU (heartbeat_check) khi SSI_* rong ===
exit=1                                    <- van chay, van toi duoc duong canh bao

=== chuong MOI (engine_consumer_check) khi SSI_* rong ===
[engine-consumer] Không thể nạp config: 'SSI_CONSUMER_ID'
exit=2                                    <- chet truoc khi nhin toi consumer
```

Chuông mới **chết trước khi kịp kiểm tra bất cứ thứ gì**, chỉ vì thiếu thông tin đăng nhập
SSI — thứ hoàn toàn không liên quan tới việc engine có tiêu thụ bar hay không.

Đây đúng bài học `51ff6de`: *một phụ thuộc mới là một cách mới để chuông chết câm*. Brief đợt
26 đã cấm phụ thuộc vào `heartbeat_check.py`; agent tránh được cái đó nhưng lại rước vào một
phụ thuộc khác còn nặng hơn.

### 1.2. Vì sao 4 test vẫn xanh — và đây mới là phần đáng lo

Cả bốn test trong `tests/test_engine_consumer_check.py` đều có dòng:

```python
    monkeypatch.setattr(ecc, "load_config", lambda *a: mock_cfg)
```

Chúng **mock đi đúng thứ giết script trong thực tế**. Bộ test xanh 100% trong khi chuông
không kêu nổi một tiếng. Một chuông báo cháy có test đầy đủ nhưng không kêu thì tệ hơn không
có chuông, vì nó tạo cảm giác an toàn giả.

### 1.3. Việc cần làm

Trong `scripts/engine_consumer_check.py`:

- Bỏ `from trading.config import load_config` và mọi lời gọi `load_config`.
- Đọc `config/config.yaml` trực tiếp bằng `yaml.safe_load`, lấy `symbols`, `holidays` —
  **cùng cách và cùng lý do** như `heartbeat_check.py:217-229`. Đọc đoạn đó rồi làm theo,
  đừng sáng tạo cách khác.
- Lấy DSN từ `os.environ.get("DB_DSN")`, thiếu thì in ra stderr và `return 2`, giống
  `heartbeat_check.py:202-205`. Bỏ phụ thuộc `_db_common.resolve_dsn`.

**Không sửa** `scripts/heartbeat_check.py`. **Không sửa** `trading/config.py`.

### 1.4. Kiểm chứng — tiêu chí thành công

1. **Phép thử quyết định, chạy thật, không mock:** đặt `DB_DSN` hợp lệ, đặt cả năm biến
   `SSI_CONSUMER_ID`, `SSI_CONSUMER_SECRET`, `SSI_API_KEY`, `SSI_API_SECRET`,
   `SSI_PRIVATE_KEY` thành chuỗi rỗng, rồi chạy `uv run python scripts/engine_consumer_check.py`.
   → Script **phải chạy tới nơi tới chốn** và trả 0 hoặc 1 tuỳ trạng thái consumer.
   → **Không được** trả 2 vì thiếu SSI. Dán nguyên văn output và exit code vào báo cáo.
2. Thêm một test **không mock `load_config`** (vì nó không còn tồn tại trong script), kiểm
   rằng thiếu biến `SSI_*` thì script vẫn tới được bước đọc consumer.
3. Bốn test cũ vẫn pass sau khi bỏ dòng mock `load_config` khỏi chúng — đây là lần **duy
   nhất** trong brief này được sửa test cũ, và chỉ được xoá đúng dòng mock đó.
4. Toàn bộ suite pass, ruff sạch.

---

## Task 2 — `BarLatch` phát lại khung đã chốt

### 2.1. Lỗ hổng, tìm được bằng phép thử phá hoại của tôi

```
=== A. Snapshot den muon SAU khi flush_due da chot khung do ===
flush_due chot: [('AAA', '09:45', 101)]
khung moi toi -> tra ve: ('09:45', 105)
  >> KHUNG 09:45 BI PHAT LAN THU HAI (gia tri khac: 101 roi 105)
```

`flush_due` xoá khung khỏi `_current_bars`. Nếu sau đó một snapshot muộn của **chính khung
đó** tới, `offer` thấy `cur is None` nên coi nó là khung mới đang mở; tới khung kế tiếp thì
khung cũ bị publish **lần thứ hai**, với giá trị khác lần đầu.

Rào chắn engine của đợt 26 **có bắt được** trường hợp này (bar trùng `ts` → WARN + bỏ qua),
nên đây không phải lỗ hổng chí mạng. Nhưng để nguyên thì mỗi lần xảy ra sẽ sinh một WARN
không đáng có, và ta mất khả năng phân biệt WARN thật với WARN do chính ta gây ra.

### 2.2. Việc cần làm

Trong `trading/collector/latch.py`: nhớ mốc khung **đã chốt gần nhất** cho từng mã. `offer`
bỏ qua (trả `None`, không ghi vào `_current_bars`) mọi snapshot có `ts` **nhỏ hơn hoặc bằng**
mốc đó. Cập nhật mốc ở cả ba nơi khung được chốt: `offer`, `flush_due`, `flush_all`.

Đồng thời **bỏ 6 dòng chuẩn hoá timezone** ở `flush_due` (dòng 63-68 của bản hiện tại):

```python
            if bar.ts.tzinfo is not None and now.tzinfo is None:
                now_cmp = now.replace(tzinfo=bar.ts.tzinfo)
            elif bar.ts.tzinfo is None and now.tzinfo is not None:
                now_cmp = now.astimezone().replace(tzinfo=None)
            else:
                now_cmp = now
```

`parse_interval_message` luôn gắn `tzinfo=TZ`, và `housekeeping_tick` truyền
`datetime.now(TZ)` — cả hai đầu vào **luôn** aware. Đây là xử lý cho tình huống không xảy ra,
đúng thứ nguyên tắc 2 trong `CLAUDE.md` cấm. Bỏ đi, so sánh thẳng `now >= threshold`.

### 2.3. Kiểm chứng

1. Test tái hiện đúng kịch bản A ở trên: `offer` → `flush_due` chốt → snapshot muộn cùng
   khung → khung mới → **không** phát lại khung cũ.
2. Test: sau `flush_all`, snapshot muộn của khung đã chốt cũng bị bỏ qua.
3. Test: khung **mới hơn** mốc đã chốt vẫn được nhận bình thường (đừng chặn nhầm).
4. Năm test `BarLatch` cũ vẫn pass **không sửa gì**.
5. Suite pass, ruff sạch, cổng cứng VN vẫn khớp từng chữ số.

---

## Task 3 — Đọc message thô phiên 10/09 (**sau 15:05**)

Nguyên văn Task 3 của brief đợt 26, chưa thực hiện. `scripts/replay_stream_check.py` đã có
sẵn từ đợt 26 — chạy nó, **không viết lại**.

Nhắc lại tiêu chí: tỷ lệ message/bar của phiên 10/09 phải **lớn hơn 1 rõ rệt** (dự kiến
5–9×), `volume` trong cùng khung tăng đơn điệu. Nếu ra ≈ 1,0 thì **dừng, báo cáo ngay**.

Đây là phép đo **trước khi sửa** — phải chạy **trước** Task 5, vì sau khi triển khai thì
không còn phiên "trước khi sửa" nào nữa. Ghi rõ dải seq đã đọc.

---

## Task 4 — Kết luận HII câm bằng số

Nguyên văn Task 6 của brief đợt 26. `scripts/.probe_hii_silent.py` đã có (đúng quy ước
`.gitignore:23` cho script probe dùng một lần). Đợt 26 chưa nộp kết luận.

**Chỉ `SELECT`, chỉ báo cáo, không sửa một dòng code nào.** Câu hỏi: điều kiện nào trong
`octopus_pullback` không bao giờ thoả với phân bố giá của HII, trong khi IJC thì thoả. Trả
lời bằng số ở từng tầng điều kiện, **không** bằng phỏng đoán.

---

## Task 5 — Triển khai (**sau 15:05**, sau khi Task 1–4 xong)

Image đang chạy vẫn là `41371bc92882` dựng ngày 08/09, tức **bản sửa lỗi bar chưa đóng chưa
hề lên sóng** — engine lúc này vẫn đang chạy chiến lược trên nến chưa đóng.

```
docker compose build collector engine
docker compose up -d --no-deps collector engine
```

1. `uv run python scripts/deploy_drift_check.py` → **exit 0**.
2. `docker compose logs --tail=50 collector` và `engine` → không `CRITICAL`, không traceback.
3. **Bằng chứng bản sửa đang chạy:** sau khi dựng lại, trong phiên kế tiếp (11/09), tỷ lệ
   message/bar phải về ≈ 1,0. Ghi nhận đây là việc của đợt sau, **không** tự ý chạy collector
   ngoài giờ để ép ra số.
4. Ghi lại `docker ps` và image ID mới.

Giữ `dot20-rollback-collector:pre` và `dot20-rollback-engine:pre`. **Không xoá.**

---

## 6. Báo cáo — và một yêu cầu về độ dài

Báo cáo đợt 26 **bị cắt giữa chừng** ở tiêu chí 5 của Task 1: không có kết quả Task 2, số
test, ruff, cổng cứng, Task 3, 6, 7, hay `git status`. Tôi phải tự chạy lại toàn bộ mới
nghiệm thu được.

Lần này: **báo cáo ngắn, đủ, theo đúng thứ tự dưới đây.** Không dán lại toàn văn output dài;
dán phần kết luận và con số. Nếu một task chưa làm, ghi thẳng "CHƯA LÀM" kèm lý do — điều đó
hữu ích hơn một báo cáo dài bị cắt mất phần cuối.

1. Output thật của phép thử Task 1.4 mục 1 (SSI rỗng) — **nguyên văn**, kèm exit code.
2. `git diff` copy từ terminal cho từng file.
3. Kết quả từng tiêu chí Task 1 và Task 2, pass/fail từng mục.
4. Số test pass + output ruff + cổng cứng VN.
5. Bảng Task 3 (tỷ lệ message/bar phiên 10/09, dải seq).
6. Kết luận Task 4 kèm số theo từng tầng điều kiện.
7. Bằng chứng triển khai Task 5.
8. `git status --short`.

**Không commit, không push.**

---

## 7. Ngoài phạm vi — quyết định của chủ dự án

Phép đo đợt 26 đã trả lời câu hỏi treo lâu nhất: **mua-và-giữ BTC cho +122,42 USDT (+24,5%)
trong khi cả bốn chiến lược đều lỗ 15–21 USDT.** Không chiến lược nào thắng được mua-và-giữ,
ở cả VN lẫn crypto.

Việc này làm Q-1 (có go-live hay không) thành câu hỏi cấp bách nhất, nhưng nó là **quyết định
của chủ dự án**, không phải việc agent. Cùng nhóm: Q-2 (`real_order_account` 0434221 rỗng,
tiền ở 0434226), Q-3 (xác nhận lệnh + đối soát), Q-5 (10/13 ngày lễ chưa khai), Q-7
(`risk_pct` cho 30x thật), chuyển VPS, scheduled task cho chuông 2C, Docker autostart.

Thấy thứ gì trong nhóm này chặn công việc → **báo cáo, không tự quyết**.
