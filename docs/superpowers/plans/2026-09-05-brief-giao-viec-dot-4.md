# Brief giao việc — đợt 4 (Q, R)

Viết 05/09 (thứ Bảy, không có phiên), sau khi đợt 3 đã xong và push (`bbd8017`).

## Đọc mục 1 trước. Nó có thể đảo một quyết định đã thực hiện.

Đợt này **chỉ có hai gói giao được cho agent**, và cả hai đều nhỏ. Phần lớn giá
trị của tài liệu này nằm ở §1 — một việc **không** giao cho agent, vì nó là việc
của chủ dự án.

---

## 1. Việc đổi engine sang octopus mâu thuẫn với phép đo đã có trong repo

### 1.1 Con số

`docs/superpowers/research/2026-09-01-strategy-comparison-v2.md` — đo trên
`bars_daily` 2.982.903 dòng, **biểu phí VN**, T+2,5 trong `PaperBroker`, mốc
mua-và-giữ cùng mã / cùng kỳ / cùng vốn / cùng phí.

Rổ đã lọc (1.308 mã, đã loại 246 mã chia tách chưa điều chỉnh):

| chiến lược | PnL | lệnh | mã sinh lệnh | mã thắng BH |
|---|---:|---:|---:|---:|
| `sma_cross` | −14.086.713.488 | 18.391 | 1.283 | 34,6% |
| `daily_breakout` | −726.392.997 | 16.198 | 1.276 | 34,7% |
| **`octopus_pullback`** | **−1.615.319.902** | **1.514** | **439** | 35,4% |

Kết luận §3 của chính báo cáo đó:

> **Không có chiến lược nào trong ba chiến lược thắng mua-và-giữ trên rổ đã lọc.**
> Engine chỉ chạy paper để hoàn thiện hạ tầng — không bật tiền thật.
> Việc đổi `engine/main.py:71` (nếu sau này có chiến lược khác **được chứng
> minh**) là task riêng.

### 1.2 Điều đã xảy ra

Ngày 04/09, theo chỉ đạo của chủ dự án, tôi đã đổi đúng dòng `engine/main.py:71`
sang octopus (`036ae1d`). Lúc đó tôi có cảnh báo, nhưng **nói quá nhẹ** — đại ý
"theo ghi chép cũ thì các chiến lược đều lỗ" — trong khi trong repo có một con số
cụ thể, mới, đã qua audit độc lập: **−1,6 tỷ trên 1.514 lệnh**.

### 1.3 Vì sao "MaxDD 2,0%" không cứu được

Điểm sáng duy nhất của octopus (25 lệnh, thắng 56%, MaxDD 2,0%, +50 triệu) đo
trên **đúng ba mã**: VCB, HPG, TCB. Khi cỡ mẫu lên 1.514 lệnh / 439 mã thì dấu
đổi chiều. Nói cách khác, cỡ mẫu lớn **đã có** và nó **mâu thuẫn** với cỡ mẫu nhỏ
— đây không phải trường hợp "chưa đủ dữ liệu để kết luận".

### 1.4 Việc của chủ dự án

> **ĐỌC THÊM TRƯỚC KHI TRẢ LỜI (thêm 05/09 chiều).** Ba lựa chọn dưới đây được
> viết khi tôi tưởng octopus đang chạy và thua. Rà soát go-live sau đó cho thấy
> nó **không chạy gì cả**: ngưỡng thanh khoản 2 tỷ là ngưỡng bar NGÀY, engine ăn
> bar 5 PHÚT, nên cổng đóng ở gần như mọi bar và engine phát **0 tín hiệu**.
> Lựa chọn 1 ("giữ octopus") vì thế hiện nghĩa là "giữ một engine câm", trừ khi
> kèm theo một ngưỡng mới — mà ngưỡng mới thì chưa ai đo (gói Y).
> Xem `2026-09-05-danh-gia-go-live-va-plan-ton-dong.md`.

Ba lựa chọn, tôi không tự chọn:

1. **Giữ octopus** — chấp nhận rằng lựa chọn này chưa có phép đo ủng hộ, và
   engine đang chạy paper nên chi phí bằng 0. Hợp lý nếu mục đích là hoàn thiện
   hạ tầng chứ không phải tìm lợi thế.
2. **Quay lại sma_cross** — cũng không có lợi thế (−14,1 tỷ), nhưng đường lệnh
   thật của nó **đối xứng** (phát cả `"bull"` lẫn `"bear"`), nên không dính mục
   tồn đọng J.
3. **Không chạy chiến lược nào** cho tới khi có cái được chứng minh.

Lưu ý cho lựa chọn 1: nó **kèm theo mục J**. Octopus không bao giờ phát `"bear"`,
nên nếu bật `real_trading_enabled` thì hệ thống chỉ MUA thật, không bao giờ BÁN
thật. Giữ octopus mà chưa xử J thì phải giữ luôn `real_trading_enabled: false`.

---

## 2. Luật chung cho hai gói dưới

### 2.1 Vai trò

Agent **viết code / thu thập bằng chứng và tự kiểm chứng**. Agent **không commit,
không push**. Claude audit rồi mới commit. Báo cáo không có bằng chứng thô thì
không được nhận.

### 2.2 An toàn — không có ngoại lệ

- `real_trading_enabled` giữ `false`. **Không bật, kể cả tạm thời.**
- Không gọi API đặt lệnh hay huỷ lệnh của SSI. Data API chỉ đọc.
- Không in giá trị bí mật ở bất kỳ đâu. Báo cáo chỉ nêu **tên biến**.
- `.env` không nằm trong git — không sửa, không commit.
- Không `TRUNCATE`, không `DROP`, không xoá dòng dữ liệu. Chỉ nạp thêm.
- **`config/config.yaml` agent không được sửa** — kể cả gói R, đặc biệt gói R.

### 2.3 Phạm vi phẫu thuật

Mỗi gói ghi rõ được sửa gì và không được đụng gì. Giữ nguyên style xung quanh.
Không "tiện thể" refactor. Phát hiện ngoài phạm vi thì **báo cáo, không sửa**.

### 2.4 Luật đơn vị — đã trả giá ba lần, đọc kỹ

Dự án này đã có **ba** lỗi cùng một hình dạng: một con số đúng trong hệ quy chiếu
này mang sang hệ quy chiếu khác mà nhìn vẫn hợp lý.

1. Lô 100 (HOSE) áp lên crypto ⇒ tài sản giá cao biến mất khỏi bảng đo.
2. `min_avg_value_20 = 2e9` **VND** áp lên giá trị **USDT** ⇒ chặn gần hết rổ,
   sinh ra câu sai "octopus không kích hoạt trên crypto".
3. `1000PEPE` (perp, đơn vị 1.000 PEPE) so với `PEPE` (spot) ⇒ lệch 1.000 lần.

Trước khi đo bất cứ thứ gì, chạy và **liệt kê trong báo cáo**:

```
grep -rn "[0-9]_000_000\|[0-9]e9\|[0-9]e8" trading/
```

Danh sách rỗng cũng phải ghi là rỗng.

### 2.5 Nền test — số hiện tại

```
uv run pytest -m "not integration" -q   ->  413 passed
docker compose --profile test up -d nats-test
uv run pytest -m integration -q         ->  100 passed
uv run ruff check trading tests scripts ->  All checks passed
```

### 2.6 GitNexus

Chỉ số đang cũ. `npx gitnexus analyze --repo AI_auto_trading_system` trước khi sửa.

### 2.7 Hai gói không dùng chung file — chạy song song được

| Gói | File sản phẩm | Chạm image? |
|---|---|---|
| **Q** | `scripts/` + `tests/` | Không |
| **R** | `docs/` (chỉ báo cáo) | Không |

---

## 3. GÓI Q — so sánh đúng rổ cho octopus

### 3.1 Vì sao gói này tồn tại

Báo cáo 01/09 tự ghi một dè dặt ở mục "Ghi chú đo lường":

> `octopus_pullback` tự lọc thanh khoản ≥ 2 tỷ trong chiến lược (748/1.308 mã đủ
> thanh khoản trên rổ đã lọc) nên **không so trực tiếp được về rổ mã** với hai
> chiến lược kia — số lệnh ít hơn ~12 lần là do bộ lọc, không phải do tín hiệu
> hiếm hơn.

Tức bảng §1.1 so octopus (439 mã sinh lệnh) với mốc mua-và-giữ của **cả 1.308 mã**.
Đó là so lệch rổ. Câu hỏi đúng chưa được trả lời:

**Trên đúng những mã mà octopus thật sự vào lệnh, nó thắng hay thua mua-và-giữ
của chính những mã đó?**

Câu trả lời không đảo được kết luận §1 (thua vẫn là thua), nhưng nó nói cho chủ
dự án biết octopus thua vì **chọn sai mã** hay vì **vào/ra sai thời điểm**. Hai
thứ đó dẫn tới hai hướng hành động khác hẳn nhau.

### 3.2 Việc ĐẦU TIÊN — kiểm xem đã có câu trả lời chưa

Cột `trung vị chênh/mã` trong báo cáo 01/09 **có thể** đã tính trên đúng tập mã
sinh lệnh. **Đọc script đã dùng và xác định.**

- Nếu đã có: **báo cáo là đã có, dẫn chứng, và DỪNG.** Không viết lại phép đo.
  Đó là kết quả hợp lệ của gói này.
- Nếu chưa có: làm tiếp §3.3.

**Không bỏ qua bước này.** Đợt 2 và đợt 3 đều có phần việc bị làm lại vì không ai
kiểm trước.

### 3.3 Việc (nếu §3.2 cho thấy chưa có)

Một script trong `scripts/`: chạy octopus trên rổ đã lọc, thu tập mã **thật sự
sinh ít nhất một lệnh**, rồi tính mốc mua-và-giữ **chỉ trên đúng tập đó**, cùng
kỳ / cùng vốn / cùng phí. Báo cáo hai con số cạnh nhau.

### 3.4 Ràng buộc cứng

- **Dùng lại `run_backtest` và cách dựng rổ lọc đã có** — không viết lại vòng đo,
  không dựng lại danh sách 246 mã loại trừ bằng tay (bài học `4ea4c8d`).
- **Giữ nguyên tham số của báo cáo 01/09**: bar ngày, biểu phí VN, T+2,5, mỗi mã
  một lần chạy độc lập vốn 1 tỷ rồi cộng dồn (không danh mục chung — tránh bẫy
  sizing). Đổi tham số thì không so được với bảng cũ.
- **Không sửa `trading/`.** Đặc biệt không đụng `min_avg_value_20` — đó là mục
  tồn đọng K, đang chờ chủ dự án.
- Chỉ ĐỌC `bars_daily`. Không ghi gì vào DB.

### 3.5 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Kiểm trước | nêu rõ script/dòng nào của báo cáo 01/09 đã (hoặc chưa) trả lời câu hỏi §3.1 |
| 2 | Tái hiện được bảng cũ | chạy octopus trên rổ đã lọc phải ra **đúng** −1.615.319.902 / 1.514 lệnh / 439 mã. Lệch là dấu hiệu tham số khác — **dừng và báo cáo**, đừng đi tiếp |
| 3 | Mốc BH đúng rổ | mua-và-giữ tính trên đúng tập mã sinh lệnh, dán nguyên văn cả hai con số |
| 4 | Quét hằng số | dán kết quả `grep` §2.4 |
| 5 | Không hồi quy | 413 + 100 |
| 6 | Lint | sạch |

**Tiêu chí 2 là cổng.** Không tái hiện được bảng cũ thì mọi con số sau đó vô nghĩa.

### 3.6 Phạm vi

- **Sửa:** `scripts/` (script mới), `tests/`.
- **Không đụng:** `trading/` toàn bộ, `config/config.yaml`,
  `scripts/measure_crypto_strategies.py`, `scripts/liquidity_sensitivity.py`,
  `scripts/bingx_spot_probe.py`, `scripts/bingx_klines.py`.

---

## 4. GÓI R — tra nguồn chính thức lịch nghỉ lễ (gỡ nút cho C3)

### 4.1 Sự thật hiện tại

`config/config.yaml:9` mới khai **ba** ngày:

```yaml
holidays: ['2026-08-31', '2026-09-01', '2026-09-02']
```

Ba ngày này không phải suy đoán — `bars_daily` có 850-980 mã mỗi ngày làm việc,
riêng ba ngày đó 0 mã, và backfill gọi SSI cũng trả rỗng.

Phần còn lại của 2026 **chưa khai**. Ngày lễ chưa khai làm chuông báo dữ liệu
kêu láo cả ngày hôm đó.

### 4.2 Việc

Tra **nguồn chính thức** cho lịch nghỉ lễ Việt Nam phần còn lại của 2026 và cho
2027 (Tết 2027 rơi vào tháng 2, cần biết sớm). Nộp danh sách ngày **kèm trích dẫn**.

### 4.3 Ràng buộc cứng — đây là gói dễ làm sai nhất

- **KHÔNG được sửa `config/config.yaml`.** Chủ dự án xác nhận, rồi Claude sửa.
- **KHÔNG bịa ngày, KHÔNG suy ra từ trí nhớ, KHÔNG dùng blog/tin tức tổng hợp.**
  Nguồn hợp lệ: văn bản của cơ quan nhà nước Việt Nam (nghị định / thông báo về
  nghỉ lễ), hoặc thông báo lịch giao dịch của HOSE / HNX / VSD.
- Mỗi ngày phải kèm **URL nguồn + đoạn trích nguyên văn** nói ra ngày đó.
- **Không tìm được nguồn có thẩm quyền thì báo là không tìm được** — kèm những
  chỗ đã thử. Đó là kết quả hợp lệ, tốt hơn một danh sách nghe hợp lý.
- Phân biệt rõ **ngày lễ theo luật** với **ngày nghỉ bù / hoán đổi** (Việt Nam
  thường xuyên hoán đổi ngày làm việc). Sàn nghỉ theo lịch thực tế, không theo
  ngày lễ danh nghĩa.
- Nếu phần còn lại của 2026 **không còn ngày lễ nào**, nói thẳng điều đó — nó có
  nghĩa C3 không gấp, và đó là thông tin có giá trị.

### 4.4 Tiêu chí

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | Có nguồn | mỗi ngày một URL + trích dẫn nguyên văn |
| 2 | Đúng loại nguồn | nguồn là văn bản nhà nước hoặc thông báo sàn, **không phải** báo/blog |
| 3 | Tách bạch | ngày lễ theo luật và ngày nghỉ bù/hoán đổi ghi riêng, không trộn |
| 4 | Đối chiếu ngược | với mỗi ngày đề xuất **đã ở quá khứ**, kiểm `bars_daily` xem hôm đó có 0 mã không — khớp thì ghi khớp, lệch thì ghi lệch |
| 5 | Trung thực | ngày nào không chắc phải nằm trong mục "chưa chắc", không nhét vào danh sách chính |

Tiêu chí 4 là phép thử rẻ mà mạnh: dữ liệu trong DB tự nó xác nhận được ngày lễ
quá khứ.

### 4.5 Phạm vi

- **Sửa:** chỉ tạo một file báo cáo trong `docs/superpowers/research/`.
- **Không đụng:** `config/config.yaml`, `trading/`, `scripts/`, `tests/`.
- Không viết code. Đây là gói tra cứu.

---

## 5. Báo cáo — định dạng bắt buộc

1. **Đã làm gì** — theo từng file, kèm số dòng.
2. **Quyết định đã chọn** — mọi chỗ có hai cách hiểu, chọn cách nào, vì sao.
3. **Output test nguyên văn** (gói Q; gói R ghi "không áp dụng").
4. **Kết quả `grep` hằng số** §2.4 (gói Q).
5. **Phát hiện ngoài phạm vi** — báo, không sửa.
6. **Điều còn chưa chắc** — nói ra, đừng giấu.

"Đã xong" không phải bằng chứng.

---

## 6. KHÔNG giao cho agent

| Mã | Vì sao |
|---|---|
| **§1 — giữ hay bỏ octopus** | Quyết định của chủ dự án. Số liệu đã đủ, không cần đo thêm. |
| **J** | Octopus chỉ MUA thật, không BÁN thật. Hai hướng sửa khác hẳn nhau — chọn hướng trước. |
| **K** | Ngưỡng thanh khoản cho USDT. Bảng độ nhạy đã có (đợt 3). Là câu hỏi kinh tế, không phải số học. |
| **F** | Spot hay perpetual. Số liệu đã có và đã đính chính (đợt 3). |
| **C3** | Gói R **thu thập nguồn**, không quyết. Chủ dự án xác nhận, Claude sửa `config.yaml`. |
| **E, C1, C2** | Vốn engine đọc nhầm tài khoản, VPS Ubuntu, Docker tự khởi động. |
| **D1** | Diễn tập dead-man's switch — cần một phiên thật. Hôm nay thứ Bảy; sớm nhất là thứ Hai 07/09. |

---

## 7. Việc KHÔNG làm

- Không bật `real_trading_enabled`, kể cả để thử.
- Không sửa `config/config.yaml` — **kể cả gói R**.
- Không sửa `min_avg_value_20` (mục K đang chờ quyết định).
- Không sửa `trading/engine/main.py` (câu hỏi §1 đang chờ quyết định).
- Không nạp lại `bars_crypto`, không tạo bảng mới.
- Không đoán ngày nghỉ lễ, không đoán phí, không đoán endpoint.
- Không commit, không push.

---

## 8. Việc của Claude, không phải của agent

Image đang **cũ hơn 6 giờ 51 phút** so với commit gần nhất chạm `trading/` (gói L,
`bb8d340`). Cả `collector` lẫn `engine` đều lệch. Hôm nay thứ Bảy, không có phiên
— dựng lại lúc nào cũng an toàn.

**Nhưng nên chờ chủ dự án trả lời §1 trước.** Nếu câu trả lời là quay lại
sma_cross thì dựng một lần là đủ cho cả hai thay đổi.
