# 2026-09-01 (đợt 6) — Phản hồi cho agent, và: triển khai code lên stack đang chạy

Hai phần. **Phần I phải đọc trước** — nó nói vì sao Phần II tồn tại.

---

# PHẦN I — Phản hồi về các brief đã làm hôm nay

Hôm nay bạn làm 5 brief. Phần lớn tốt, và phần tốt nhất là **kỷ luật từ chối
sửa mù**: đợt 5 bạn không đụng backoff của lỗi thường; đợt 4 bạn giữ nguyên
tham số chiến lược; đợt 3 bạn dừng ở cổng chặn A3 thay vì đoán. Đó đúng là
điều khó nhất và bạn làm được.

Nhưng có một khuôn mẫu lặp lại **ba lần** trong một ngày, và nó nghiêm trọng.

## 1. Ba lần báo cáo chứa số không tái lập được

**Đợt 3 — "FEED ĐÃ HỒI".** Kết luận dựa trên "0 lỗi từ 12:10:54". Nhưng
12:10–12:23 là **giờ nghỉ trưa** — không có tick nào để mà lỗi, và
`Watchdog.check()` cũng thoát sớm ngoài giờ. Bằng chứng rỗng được trình bày như
bằng chứng mạnh.

**Đợt 4 — bảng đối đầu VCB/HPG/TCB.** Báo cáo ghi 113/103/23 lệnh và mua-và-giữ
`11.844.464.091`. Chạy lại đúng tham số ra 61/72/25 lệnh và `3.948.143.113` —
PnL trùng bảng 15/08 **tới từng đồng**. Nghiêm trọng hơn con số sai: báo cáo còn
**giải thích** nó ("đợt nạp lại back-adjust làm BH gấp 3 lần, sma_cross 61→113
lệnh"). Một lời giải thích hợp lý cho một hiện tượng không tồn tại.

**Đợt 5 — "Task C thực địa: restart collector 14:41:12, 0 lỗi".** Container có
restart thật lúc đó. Nhưng nó chạy image build **2026-08-15**:

```
docker exec ai_auto_trading_system-collector-1 sh -c \
  'grep -c _connected $(python -c "import trading.collector.feed as m; print(m.__file__)")'
→ 0
```

Bạn quan sát **code cũ**. Task C không nói được gì về bản sửa. (Và có 1 dòng
`forcing reconnect` lúc 14:44:33, không phải "0".)

### Điểm chung

Cả ba đều là **quan sát thật, diễn giải sai**, không phải bịa số. Nhưng hậu quả
giống nhau: một kết luận sai được trình bày với đầy đủ vẻ ngoài của bằng chứng.
Và cả ba đều bị bắt bằng **đúng một cách**: chạy lại và đối chiếu số.

**Ba câu phải tự hỏi trước khi viết "đã kiểm chứng":**

1. *Phép đo này có khả năng cho kết quả này ngay cả khi bản sửa không tồn tại
   không?* Nếu có — nó không kiểm chứng gì cả. (Đợt 3: giờ nghỉ trưa. Đợt 5:
   code cũ.)
2. *Số này tôi chạy ra, hay tôi nhớ/suy ra?* Nếu không dán được output nguyên
   văn thì đừng viết nó vào bảng.
3. *Nếu tôi phải giải thích một con số bất ngờ, tôi đã kiểm nó chưa?* Một con số
   lệch 3 lần là tín hiệu phải **đo lại**, không phải tín hiệu phải **giải
   thích**. Đợt 4 sai đúng ở chỗ này.

## 2. Test chớp chờn — đợt 5

Ba test backoff đo đồng hồ thật với cap 0.05s. Chạy full-suite hai lần cho
**hai test khác nhau** đỏ:

```
AssertionError: cap phai giu nguyen: [0.031, 0.031, 0.047, 0.047, 0.062]
```

Độ phân giải timer Windows ~15,6ms. Và comment trong test **tự thừa nhận** đã
nới ngưỡng vì "full-suite làm overhead đẩy gap lên" — đó là **giấu vấn đề**.

Nguyên tắc: khi bạn thấy mình đang nới ngưỡng cho test hết đỏ, dừng lại. Gần
như luôn luôn nghĩa là **đang đo sai đại lượng**. Ở đây đại lượng cần đo là một
phép tính số học (`backoff` tính ra bao nhiêu), không phải một khoảng thời gian.
Đã thay bằng spy ghi thẳng `timeout` truyền vào `asyncio.wait_for` — không ngủ
giây nào, dùng được số production thật (cap 600s), và khẳng định thành số chính
xác `[2, 4, 8, 16, 32, 64] ... max == 600.0`.

**Test chớp chờn tệ hơn không có test:** nó dạy người ta quen bỏ qua màu đỏ.

## 3. Hai điều nhỏ

- Đợt 5 báo "main.py + test_collector_main.py còn M — thay đổi dư từ đợt 3 chưa
  commit". Sai: đợt 3 đã commit (`ed17539`) và tree sạch. Vô hại, nhưng kiểm
  `git log` trước khi mô tả trạng thái repo.
- Đợt 4 báo "334 passed" khi HEAD lúc đó cho 336. Đo trước khi fetch.

## 4. Điều KHÔNG phải lỗi của bạn

Việc container chạy image 15/08 **có từ trước** mọi brief hôm nay. Bản sửa đợt 3
(`ed17539`), sizing theo NAV (`6159d39`), GUARD-3 — **chưa cái nào từng chạy
thật**. Không ai kiểm, kể cả tôi. Đó là lý do Phần II tồn tại.

---

# PHẦN II — Brief đợt 6: triển khai và kiểm chứng thực địa THẬT

## 1. Vấn đề, đo được

```
image collector/engine created : 2026-08-15T04:17:10Z
grep _connected trong container            → 0
grep _restart_feed_and_alert trong container → 0
```

Mọi thay đổi trong `trading/` từ 15/08 tới nay **chưa từng chạy**. Chỉ
`scripts/` có hiệu lực, vì chúng chạy trên host qua Task Scheduler chứ không
trong container.

Danh sách chưa triển khai (không đầy đủ): `6159d39` sizing lệnh thật theo NAV +
GUARD-3, `ed17539` watchdog thôi kêu hành động không xảy ra, `f8e3392` backoff
429 + cờ `_connected`.

## 2. Cửa sổ thời gian — vì sao là bây giờ

**01/09 và 02/09 là nghỉ lễ Quốc khánh; phiên kế tiếp là 03/09.** Feed không có
việc gì để làm, không có bar nào để mất. Đây là cửa sổ an toàn nhất để dựng lại
container. Làm giữa phiên là tự chuốc rủi ro không cần thiết.

## 3. Môi trường

- Windows 11, PowerShell + Git Bash. Repo:
  `D:\My_Vault_Obsidian\Project\AI_auto_trading_system`.
- **`git pull` trước khi làm** — HEAD hiện tại là `f8e3392`, có bản sửa đợt 5 đã
  được audit và commit (khác bản trong working tree của bạn).
- Truy vấn DB:
  `docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "..."`
- Lệnh quá 10 phút bị cắt — `docker compose build` có thể lâu, chạy tách rời rồi
  theo dõi log.
- Không in giá trị secret ra bất cứ đâu.

## 4. Phạm vi

**Task này KHÔNG sửa code.** Không file nào trong `trading/`, `scripts/`,
`tests/`, `config/` được thay đổi.

Nếu quá trình dựng lại làm lộ ra lỗi (container không lên, import lỗi, config
thiếu): **báo cáo và dừng**, đừng vá. Một lỗi lộ ra lúc dựng lại là **phát hiện
có giá trị** — nó chứng minh code đã trôi khỏi thứ đang chạy suốt hai tuần.

## 5. Các bước

### Bước 1 — Chụp trạng thái trước

Ghi lại, dán nguyên văn:
- `docker compose ps`
- `docker inspect -f '{{.Created}}' $(docker inspect -f '{{.Image}}' ai_auto_trading_system-collector-1)`
- `SELECT service, last_seen FROM heartbeat;`
- `SELECT max(ts) FROM bars;` và `SELECT max(ts) FROM bars_daily;`

→ Hai truy vấn cuối là **mốc so sánh sau khi dựng lại**. Dữ liệu không được mất.

### Bước 2 — Dựng lại

```
docker compose up -d --build collector engine
```

Chỉ hai service này. **KHÔNG** đụng `postgres`, `nats`, `grafana`. **KHÔNG**
`docker compose down`. **KHÔNG** xoá volume.

→ **Kiểm chứng:** cả hai container `running`, và `image Created` là hôm nay.

### Bước 3 — Chứng minh code MỚI thật sự nằm trong container

Đây là bước mà đợt 5 đã bỏ qua, và là lý do brief này tồn tại.

```
docker exec ai_auto_trading_system-collector-1 sh -c \
  'grep -c _connected $(python -c "import trading.collector.feed as m; print(m.__file__)")'
docker exec ai_auto_trading_system-collector-1 sh -c \
  'grep -c _restart_feed_and_alert $(python -c "import trading.collector.main as m; print(m.__file__)")'
docker exec ai_auto_trading_system-collector-1 sh -c \
  'grep -c backoff_cap_429 $(python -c "import trading.collector.feed as m; print(m.__file__)")'
```

→ **Kiểm chứng:** cả ba **> 0**. Nếu còn 0 thì build không lấy source mới —
**dừng lại, báo cáo**, đừng restart lại cho tới khi hiểu vì sao.

### Bước 4 — Dữ liệu không mất

Chạy lại hai truy vấn của Bước 1.

→ **Kiểm chứng:** `max(ts)` của `bars` và `bars_daily` **không đổi**. Đổi = có
chuyện, dừng và báo cáo ngay.

### Bước 5 — Quan sát 30 phút

Theo dõi log collector và engine.

→ **Kiểm chứng, dán nguyên văn:**
- Bảng mốc giờ mọi dòng `SSIFeed connection error`, `feed stale, forcing
  reconnect`, `HTTP 429` trong 30 phút.
- `SELECT service, last_seen FROM heartbeat;` — cả hai phải tươi trở lại.
- Có dòng GUARD nào của engine không (`6159d39` thêm GUARD-3) — dán nguyên văn.

→ **Đọc kết quả — đọc kỹ, đây là chỗ dễ sai nhất:**
- Hôm nay **nghỉ lễ**, nên `Watchdog` sẽ **không** kêu (`is_trading_fn` có nhận
  `cfg.holidays`, và `config.yaml` đã có `2026-09-01`). **Im lặng hôm nay KHÔNG
  chứng minh backoff 429 hoạt động** — nó chỉ chứng minh container lên được và
  không sập. Nói đúng như vậy trong báo cáo.
- Kiểm chứng thật của backoff 429 chỉ có thể xảy ra khi có 429 thật. **Không
  được cố tình gây ra.** Ghi "chưa quan sát được" là kết cục hợp lệ.

### Bước 6 — Ghi vào `DEPLOYMENT.md`

Thêm một mục ngắn: **sau khi sửa code trong `trading/`, phải dựng lại container
— sửa file trên host không làm gì cả**, kèm đúng ba lệnh `grep` ở Bước 3 làm
cách kiểm chứng. Đặt cạnh mục lịch chạy.

Đây là file **duy nhất** được sửa trong brief này.

→ **Kiểm chứng:** dán đoạn đã thêm.

## 6. Cấm

- **Không commit, không push.** Claude audit rồi mới commit.
- **Không sửa code** trong `trading/`, `scripts/`, `tests/`, `config/`.
- **Không bật `real_trading_enabled`.** Đã có kết luận `711683a`: không chiến
  lược nào thắng mua-và-giữ, engine chỉ chạy paper. Sau khi dựng lại, code
  sizing theo NAV (`6159d39`) mới thật sự chạy — càng phải giữ cờ này `false`.
- **Không `docker compose down`**, không đụng `postgres`/`nats`/`grafana`, không
  xoá volume.
- Không gọi API đặt/huỷ lệnh SSI.
- **Không cố tình gây 429.**
- Không in giá trị secret.
- Vấn đề ngoài phạm vi: **báo cáo**, không tự sửa.

## 7. Tiêu chí hoàn thành

- Bước 1 và 4: hai bộ số `max(ts)` đặt cạnh nhau, chứng minh dữ liệu không đổi.
- Bước 3: **ba con số `grep` đều > 0** — không có cái này thì task chưa xong,
  bất kể container có chạy hay không.
- Bước 5: bảng mốc giờ 30 phút, và **một câu nói rõ hôm nay là ngày nghỉ nên
  im lặng chứng minh được gì và KHÔNG chứng minh được gì**.
- Bước 6: đoạn `DEPLOYMENT.md` đã thêm.
- Việc nào không làm được thì nói rõ vì sao.

> Nhắc lại Phần I: báo cáo sẽ được kiểm bằng cách chạy lại và đối chiếu số. Số
> nào bạn không thật sự chạy ra thì đừng viết. **"Chưa đo được" luôn là câu trả
> lời chấp nhận được; một phép đo bịa thì không.**
