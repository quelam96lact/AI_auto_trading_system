# Brief đợt 57 — Tuần go-live 22–26/09

Ngày giao: 19/09/2026 (thứ Bảy).
Base: `0c31576` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Hai sự thật phải nói trước, không giấu trong phụ lục

### 0.1. Cổng cứng nói chiến lược này LỖ

```
TONG: strat -1,615,319,902 | BH 1,897,587,481,903 | lenh 1,514 | ma sinh lenh 439
```

Chiến lược **âm**, và kém buy-and-hold khoảng **1,9 nghìn tỷ** trên vũ trụ đo. Tám chiến lược
crypto đợt 37–44 cũng đều âm. Không có phép đo nào trong repo này nói rằng nó kiếm được tiền.

Nên phải định nghĩa lại "go live" cho đúng:

| | |
|---|---|
| **Là gì** | Chứng minh **đường ống** chạy trọn một vòng bằng tiền thật, kích thước tối thiểu, mỗi lệnh có người gật |
| **Không là gì** | Triển khai một chiến lược có lợi thế đo được |

Tuần này làm được vế trái. Vế phải là **Q-1**, và nó không được giải bằng cách bật một cái cờ.

Điều làm vế trái vẫn đáng làm: một đường lệnh chưa từng chạy trọn vòng là **rủi ro kỹ thuật chưa
đo được**, và không backtest nào đo hộ. Chạy nó với 100 cổ phiếu (~700 nghìn đồng) là cách rẻ
nhất để biến ẩn số đó thành dữ kiện.

### 0.2. Engine đã 15 ngày không sinh tín hiệu

```
2026-08-14 |  5 tin hieu
2026-08-19 |  3
2026-09-04 |  1
(sau do: khong co gi)
```

**Kế hoạch không được phụ thuộc vào việc một tín hiệu tự đến trong tuần.** Nếu cả tuần engine
câm thì lịch dưới đây vẫn phải tiến được — đó là lý do bước đầu tiên không dùng tín hiệu.

### 0.3. Và thứ mở khoá cả kế hoạch: bài kiểm đã viết sẵn, chưa ai chạy

`scripts/spike_ssi_sdk_place_order.py` — viết từ Phase 0, **chưa chạy lần nào** (không có file
kết quả `.spike_cancel_order.json`). Nó làm đúng năm bước, theo đúng thứ tự:

```
1. get_max_buy_sell_at_market_price()   CHI DOC, du 100cp thi moi di tiep
2. lay gia dong cua that qua AsyncData  CHI DOC, khong tu doan gia
3. dat 1 lenh LIMIT mua o 93% gia dong cua
   (trong bien do +-7% nen san nhan, nhung gan nhu chac chan KHONG khop)
4. cancel_order() ngay lap tuc, xac nhan huy thanh cong
5. KHONG goi bat ky API nao khac ngoai place_limit_order + cancel_order
```

Lý do nó chưa chạy nằm trong chính docstring: *"account Cash 0434221 hiện chỉ ~21,459đ"*. **Trở
ngại đó đã hết** — hôm nay `0434221` có NAV **5.021.712đ**, sức mua **217 HPG / 676 IJC / 645 AAA**,
và cả hai lá chắn độ tươi đều `ĐẠT`.

Đây là bước một của tuần go-live: nó chứng minh `place_limit_order` + `cancel_order` chạy thật
với chứng chỉ thật trên sàn thật, mà **không cần tín hiệu nào** và **gần như không có rủi ro vị thế**.

---

## 1. Lịch tuần, và cổng chặn từng ngày

Mỗi ngày có một **cổng**. Không qua cổng thì **không sang ngày sau** — lùi lịch, không bỏ bước.

| Ngày | Việc | Ai làm | Cổng phải qua |
|---|---|---|---|
| **T7–CN 19–21/09** | `holidays` vào config; `powercfg`; agent làm Task 1–3 | Chủ dự án + agent | `powercfg` xong trước 20:00 CN |
| **T2 22/09** | Phép đo đợt 52 (giao thức 4 bước ở báo cáo đợt 55) | Claude + chủ dự án | `bars_closed.log` có dòng `bars closed` thật; độ phủ ≥ 90% |
| **T3 23/09 (ngoài phiên)** | Chạy `spike_ssi_sdk_place_order.py` | **Chủ dự án bấm nút**, Claude giám sát | Đặt được **và** huỷ được; `.spike_cancel_order.json` có kết quả |
| **T4 24/09** | Diễn tập cửa xác nhận trên `trading_test`, **bấm giờ** | Chủ dự án | Hoàn tất dưới **15 phút** kể từ lúc tin Telegram tới |
| **T5 25/09** | Bật `real_trading_enabled: true`, tài khoản `0434221` | Chủ dự án | Mọi lá chắn `ĐẠT` lúc 08:45 |
| **T6 26/09** | Đánh giá, giữ hoặc tắt | Chủ dự án | — |

**Vì sao `0434221` chứ không phải `0434226`:** NAV 5,0 triệu so với 182,9 triệu. Tuần này đo
đường ống chứ không đo lợi nhuận, nên chọn tài khoản mà **sai lầm tệ nhất vẫn nhỏ**. Đó cũng là
câu trả lời tôi đề xuất cho Q-2. Nếu chủ dự án muốn `0434226` thì nói trước T5, đừng đổi giữa chừng.

**Nếu cả tuần engine không sinh tín hiệu:** T5 vẫn bật cờ, và kết quả tuần là *"đường ống đã
chứng minh tới bước đặt/huỷ thật, chưa chứng minh tới bước khớp"*. Đó là kết quả **hợp lệ**, ghi
đúng như vậy, đừng ép một tín hiệu giả để có cái báo cáo đẹp.

---

## 2. Phạm vi

| File | Trạng thái | Task |
|---|---|---|
| `scripts/docker_down_alert.py` | có sẵn — **gỡ cấm riêng cho Task 2** | 2 |
| `tests/test_docker_down_alert.py` | có sẵn | 2 — **chỉ thêm** |
| `scripts/engine_consumer_check.py` | có sẵn — **gỡ cấm riêng cho Task 2** | 2 |
| `tests/test_engine_consumer_check.py` | có sẵn | 2 — **chỉ thêm** |
| `scripts/check_golive_gate.py` | **mới** | 3 |
| `tests/test_check_golive_gate.py` | **mới** | 3 |
| `docs/superpowers/research/2026-09-19-dot-57-*.md` | **mới** | báo cáo |

**Task 1 không sửa file nào** — đọc và soạn.

**Không đụng:** `scripts/heartbeat_check.py`,
`scripts/spike_ssi_sdk_place_order.py` (**tuyệt đối không sửa — nó sắp đặt lệnh thật**),
`scripts/confirm_real_order.py`, `trading/real_orders.py`, `trading/alerts.py`,
`trading/calendar_vn.py`, `PaperBroker`, `trading/risk.py`, `trading/strategies/*`,
`trading/engine/logic.py`, `config/config.yaml`.

Ràng buộc chung: `real_trading_enabled` giữ **`false`** trong suốt đợt này — **việc bật là của
chủ dự án ở T5, không phải của agent**; **không gọi SSI, không đặt lệnh, không huỷ lệnh**; không
in secret; `.env` không sửa/không mở để đọc giá trị; **chỉ đọc DB**; **không** `delete`/`purge`/
`add`/`update` stream hay consumer NATS nào; **không dựng lại container, không build image**;
**không đăng ký/sửa Scheduled Task**; không xoá file; **không commit, không push**. Mọi `git diff`
copy từ lệnh. Thiếu thì ghi **"CHƯA LÀM"**, **không bịa**.

---

## Task 1 — Đọc kỹ bài kiểm đặt/huỷ lệnh, và nói nó sẽ làm gì

**Đọc thuần. KHÔNG chạy. KHÔNG sửa.** Script này đặt lệnh thật lên sàn; nó chỉ được chạy ở T3
với chủ dự án ngồi cạnh.

Việc của bạn là để chủ dự án bấm nút mà **biết trước chính xác chuyện gì sẽ xảy ra**. Trả lời:

1. **Nó sẽ đặt lệnh gì, mã nào, giá bao nhiêu, khối lượng bao nhiêu?** Tính ra con số cụ thể
   bằng giá đóng cửa gần nhất trong DB cho từng mã trong `cfg.symbols`. Nêu cả **số tiền tối đa
   bị chiếm** nếu lệnh lỡ khớp.
2. **Điều kiện tiền đề nào phải đúng trước khi chạy?** Liệt kê đầy đủ (token, biến môi trường,
   sức mua, giờ chạy). Với mỗi điều, nêu **lệnh kiểm** và **kết quả hiện tại**.
3. **Nếu bước 4 (huỷ) thất bại thì sao?** Đây là câu quan trọng nhất. Đọc code và trả lời: lệnh
   còn treo trên sàn hay không, ai phải làm gì, và script có nói rõ điều đó ra không.
4. **Chạy lúc nào?** Trong phiên hay ngoài phiên? Đọc code để biết nó có tự chặn theo giờ không.
   Nêu khung giờ bạn khuyến nghị và **lý do từ code**, không phải cảm giác.
5. **Có chỗ nào trong script đã lỗi thời** so với hệ thống hôm nay không? Nó viết từ Phase 0,
   trước rất nhiều đợt. Ví dụ đáng ngờ: docstring nói tài khoản chỉ có ~21.459đ. Đối chiếu mọi
   giả định của nó với trạng thái thật. **Phát hiện thì báo cáo, tuyệt đối không sửa.**

Kết luận một trong hai: **CHẠY ĐƯỢC Ở T3** (kèm lệnh chính xác và khung giờ), hoặc **CHƯA**
(kèm việc phải làm trước).

---

## Task 2 — Chuông tự khoá miệng sau khi gửi trượt (HAI file)

**Đây là lý do tôi gỡ cấm `engine_consumer_check.py` và `docker_down_alert.py` cho riêng task này.**

### 2.0. Và một hồi quy do chính đợt 56 gây ra — cái này gấp hơn

Tôi tìm ra khi tự soát brief này, không phải từ báo cáo nào.

`docker_down_alert.py:128-139` viết từ đợt 8 và **từng đúng**:

```python
_print_safe(msg)
try:
    send(msg)
except Exception as e:                                    # <- nhanh nay
    _print_safe(f"[docker-down-alert] gui Telegram loi: ...")
    return 0                                              # <- thoat TRUOC khi ghi dau
_write_last_alert(now, stamp_file)                        # <- chi ghi khi gui xong
```

Nó cố tình `return 0` **trước** `_write_last_alert` khi gửi hỏng — đúng luật "chỉ ghi dấu khi đã
gửi được". Bằng chứng nó từng chạy: dòng `[docker-down-alert] gui Telegram loi: URLError` trong
`logs/heartbeat.log` ngày 16/09.

**Đợt 56 làm `send_telegram` thôi ném và trả `False`.** Hệ quả không ai để ý:

1. Nhánh `except` thành **code chết** — không bao giờ chạy nữa.
2. `_write_last_alert` giờ chạy **kể cả khi gửi trượt**.
3. Dòng `"gui Telegram loi: ..."` từ nay **không bao giờ xuất hiện nữa**.

Tức là bản vá đợt 56 — thứ sinh ra để chuông thôi hỏng câm — vừa **làm câm đi một chuông đã đúng**.
Và nó là chuông **"Docker chết"**, cái mà thông điệp của nó tự nói: *"đây là tin nhắn DUY NHẤT
bạn sẽ nhận"*. Gửi trượt mà vẫn đóng dấu thì tin duy nhất ấy mất, và hàng rào chặn luôn lần thử lại.

Đây là cái giá của việc đổi hợp đồng một hàm có tám nơi gọi: tôi đã kiểm "không nơi nào **dùng**
giá trị trả về" và kết luận tương thích ngược. Đúng về giá trị trả về, **sai về hành vi ném**. Một
nơi đang dựa vào việc nó **ném**.

Báo cáo đợt 56 Task 2 tìm ra: script cập nhật `last_alert_ts` **kể cả khi `send_telegram` trả
`False`**. Hệ quả: mạng hỏng đúng lúc chuông định kêu → tin không đi → **và chuông tự khoá miệng
15 phút nữa**. Một lần trượt thành hai lần im.

Điều này đã có tiền lệ thật: ngày 14/09 và 16/09, `send_telegram` hỏng vì DNS (`getaddrinfo
failed`) — đúng loại sự cố xảy ra khi máy vừa ngủ dậy, tức là **đúng lúc ta cần chuông nhất**.

### 2.1. Luật, áp cho cả hai file

**Chỉ ghi dấu chống spam khi đã gửi được.** `send_telegram` giờ trả `bool`, nên:

```
gui duoc       -> ghi dau, im theo chu ky chong spam (nhu cu)
gui khong duoc -> KHONG ghi dau, de lan sau con thu lai
```

| File | Chỗ sửa | Việc |
|---|---|---|
| `docker_down_alert.py` | `:134-138` | `if send(msg): _write_last_alert(...)`; **bỏ nhánh `except` đã chết**, hoặc giữ lại và nói rõ vì sao |
| `engine_consumer_check.py` | `:174-177` | `if send_telegram(alert_msg): new_state["last_alert_ts"] = ...` |

**Thứ tự: sửa `docker_down_alert` trước** — nó là hồi quy vừa gây ra, còn cái kia là lỗi có sẵn.

Lưu ý `docker_down_alert.run_alert` nhận `send=send_telegram` làm tham số, nên test được bằng
cách truyền hàm giả trả `True`/`False`. Đừng monkeypatch, dùng đúng tham số đã có.

### 2.2. Ràng buộc phẫu thuật

- **Chỉ sửa phần quyết định có ghi dấu hay không.** Không đổi ngưỡng, không đổi mã thoát, không
  đổi thông điệp, không refactor gì khác trong file.
- Ba chỗ gọi `send_telegram` trong file (`:132`, `:147`, `:176`) — đọc cả ba, xác định chỗ nào
  thật sự gắn với `last_alert_ts`. **Đừng sửa cả ba nếu chỉ một chỗ liên quan.** Tôi đã đọc và
  chỉ thấy **một** chỗ, ở khối này:

  ```python
  # scripts/engine_consumer_check.py:174-177
  if cooldown_elapsed >= ALERT_COOLDOWN_SECONDS:
      send_telegram(alert_msg)
      new_state["last_alert_ts"] = now.timestamp()     # <- vo dieu kien
  ```

  Bạn vẫn phải tự kiểm, nhưng nếu kết luận của bạn khác tôi thì **nói ra trước khi sửa**.

- Chú ý một điều **đã đúng sẵn** trong khối đó: `_print_safe(alert_msg)` chạy **trước** khi gửi,
  đúng khuôn `FEE-ALARM-2`. Giữ nguyên, đừng "dọn" nó.
- Chạy `gitnexus_impact` trước khi sửa.

### 2.3. Kiểm chứng

1. Test mới (**chỉ thêm**): `send_telegram` giả trả `False` → `last_alert_ts` **không đổi**;
   trả `True` → **có đổi**.
2. **Chứng minh test phân biệt được:** tạm khôi phục hành vi cũ → test **đổ**; khôi phục → suite
   xanh và `git diff` của file đó khớp đúng phần bạn định sửa.
3. Suite đầy đủ pass (mốc **792**), ruff sạch.

---

## Task 3 — Một cổng kiểm trước khi bật cờ

T5 là lúc chủ dự án đổi `real_trading_enabled` thành `true`. Trước khi đổi, cần **một lệnh** trả
lời được "có an toàn để bật không", thay vì phải nhớ mười thứ.

### 3.1. `scripts/check_golive_gate.py`

**Chỉ đọc. Không gọi SSI. Không sửa gì. Không gửi Telegram.**

In một bảng và trả mã thoát: `0` = bật được, `1` = có cảnh báo cần đọc, `2` = **không được bật**.

Kiểm tối thiểu những điều này, và **mỗi điều phải lấy từ nguồn thật, không hằng số**:

| Kiểm | Nguồn | Ngưỡng |
|---|---|---|
| `real_trading_enabled` hiện tại | `config/config.yaml` | in ra giá trị, không đổi |
| Tài khoản cấu hình và NAV | `account_nav_snapshot` | in ra |
| Sức mua đủ ≥ 100 cp cho từng mã | `account_buying_power` | đủ cả 3 mã |
| Tuổi bản ghi vị thế | `account_sync_log` | ≤ 15 phút |
| Tuổi bản ghi sức mua | `account_buying_power` | ≤ 15 phút |
| Độ phủ luồng phiên gần nhất | `logs/stream-health.log` hoặc `stream_health_check` | ≥ 90% |
| Đường Telegram | `send_telegram` trả `bool` | **không gửi tin** — chỉ kiểm biến môi trường có mặt |
| Lệch triển khai | `deploy_drift_check` | exit 0 |
| Số lệnh thật đã khớp | `real_order_fills` | in ra, không chặn |

**Đừng viết lại những phép kiểm đã có.** `check_real_order_readiness.py` đã làm phần lá chắn;
`deploy_drift_check.py` đã làm phần image. Gọi lại/đọc lại chúng, **đừng chép logic**. Nếu bạn
thấy mình copy một đoạn kiểm từ script khác sang, đó là dấu hiệu làm sai — báo cáo và đề xuất
cách gọi lại thay vì chép.

### 3.2. Điều cổng này **không** được làm

- **Không tự bật cờ.** Nó chỉ nói "được/không được".
- **Không gửi Telegram.** Kiểm biến môi trường có mặt là đủ; gửi thật là việc của T3/T4.
- **Không gọi SSI.** Mọi thứ đọc từ DB và file.
- **Không đánh giá chiến lược.** Cổng này nói về **đường ống**, không nói về lợi nhuận. Nếu bạn
  thấy mình định thêm một dòng kiểu "chiến lược có lãi không" — dừng, đó là Q-1, không phải việc
  của một script.

### 3.3. Kiểm chứng

1. Chạy thật, dán nguyên văn bảng và mã thoát.
2. Test cho **hàm thuần đánh giá** (tách phần quyết định khỏi phần đọc DB, như
   `evaluate_daily_completeness` đã làm): đủ điều kiện → `0`; một điều cảnh báo → `1`; lá chắn
   quá hạn → `2`.
3. Suite đầy đủ pass, ruff sạch.

---

## 3. Báo cáo cho Claude

1. `git diff --stat`, `git status --short`.
2. Task 1: năm câu trả lời, kết luận hai lựa chọn, **lệnh chính xác để chạy ở T3**.
3. Task 2: `gitnexus_impact`, `git diff`, bằng chứng test phân biệt được.
4. Task 3: nguyên văn một lượt chạy thật, `git diff` file mới.
5. Ba dòng: số test pass (mốc **792**), ruff, cổng cứng VN đủ bốn con số.

**Không commit, không push. Không bật `real_trading_enabled`. Không đặt lệnh.**

---

## 4. Điều KHÔNG thuộc phạm vi

- **Không chạy `spike_ssi_sdk_place_order.py`** — T3, có chủ dự án.
- **Không bật `real_trading_enabled`** — T5, chủ dự án.
- **Không sửa** `spike_ssi_sdk_place_order.py`, `confirm_real_order.py`, `real_orders.py`.
- **Không gom `is_trading_day`** vào bốn hàm còn lại của `calendar_vn` — để sau phép đo T2.
- **Không sửa** tham số bị che tên trong `daily_data_check` (mục D đợt 56) — để sau.
- **Không che `chat_id` trong probe** — việc nhỏ, để sau tuần go-live.

---

## 5. Việc của chủ dự án, xếp theo ngày

**Trước 20:00 Chủ nhật 21/09 — hai việc, cả hai đều chặn:**

1. **`powercfg /change standby-timeout-dc 0`.** Máy ngủ tối Chủ nhật → backfill 20:30 chết →
   thứ Hai thiếu dữ liệu → phép đo T2 hỏng và cả tuần lùi một nhịp. Nguyên nhân này đã được
   chứng minh bằng Kernel-Power ở đợt 52, không còn là giả thuyết.
2. **Bổ sung `holidays` trong `config/config.yaml`.** Danh sách hiện chỉ có `2026-08-31`,
   `2026-09-01`, `2026-09-02` — **toàn ngày đã qua**. Sau đợt 55–56, đây là thứ duy nhất chặn
   báo động giả vào ngày lễ giữa tuần. Cần lịch nghỉ còn lại 2026 và cả 2027.

**T3 23/09:** bấm nút chạy bài kiểm đặt/huỷ lệnh thật, sau khi đọc Task 1.

**T4 24/09:** diễn tập cửa xác nhận, **bấm giờ**. Câu hỏi cần trả lời bằng trải nghiệm: **15 phút
có đủ không?** Nếu không đủ, nói ra trước T5 — đổi TTL dễ hơn nhiều so với lỡ một lệnh thật.

**T5 25/09:** bật cờ, sau khi `check_golive_gate.py` trả `0`.

**Còn mở, không chặn tuần này:** Q-1 (chiến lược có lợi thế không), `README.md` 253 dòng,
`DELETE` dòng `TEST` trong `orders`.
