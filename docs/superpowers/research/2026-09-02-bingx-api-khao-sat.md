# Khảo sát API BingX — dữ kiện để lập kế hoạch

Đọc 02/09/2026 từ tài liệu chính thức. Bổ sung cho
`2026-09-02-tong-hop-ton-dong-va-danh-gia-bingx.md`.

Nguồn: `https://bingx-api.github.io/docs-v3/`, kho
`github.com/BingX-API/api-ai-skills` (cập nhật 24/08/2026), và trang hỗ trợ
BingX.

---

## 1. FOREX KHÔNG CÓ TRONG API — phạm vi phải thu lại

Yêu cầu ban đầu là "crypto **và forex** trên BingX". Kiểm chứng:

- Thư viện skill chính thức của BingX có **29 module**, không module nào
  nhắc tới forex/CFD (`grep -ci "forex\|cfd" = 0`).
- Các phân khúc có API: **spot**, **hợp đồng vĩnh cửu USDT-M** (`swap`),
  **hợp đồng ký quỹ bằng coin** (`cswap`), `standard-trade`, copy trading,
  tài khoản/ví/tài khoản con.
- Trang hỗ trợ BingX nói thẳng: *"The API management tool currently supports
  API services for **Spot and Perpetual Futures**."*

**Kết luận: chỉ làm được crypto.** Forex trên BingX (nếu có trên giao diện
web) không có đường API để hệ thống tự động giao dịch. Nếu forex là mục tiêu
bắt buộc thì phải chọn sàn khác — và đó là quyết định của chủ dự án, không
phải việc kỹ thuật.

---

## 2. CÓ MÔI TRƯỜNG MÔ PHỎNG THẬT (testnet) — dữ kiện tốt nhất tìm được

| Môi trường | Base URL chính | Dự phòng |
|---|---|---|
| `prod-live` | `https://open-api.bingx.com` | `https://open-api.bingx.pro` |
| `prod-vst` (mô phỏng) | `https://open-api-vst.bingx.com` | `https://open-api-vst.bingx.pro` |

Tài liệu ghi rõ: *"Use `prod-vst` for paper trading / testing without real
funds."*

**Vì sao đây là dữ kiện quan trọng nhất trong cả bản khảo sát:** hệ thống hiện
tại kiểm chứng đường đặt lệnh bằng `PaperBroker` tự viết — một mô phỏng của
*ta*, không phải của sàn. Với BingX có thể chạy **đường đặt lệnh thật, khớp
lệnh thật, mã lỗi thật**, chỉ khác là tiền giả. Toàn bộ lớp rủi ro "code đặt
lệnh chưa từng chạy thật" — thứ đã khiến dự án này phải dựng `real_orders.py`
rồi không dám bật — biến mất.

`PaperBroker` vẫn cần cho **backtest** (chạy trên lịch sử), nhưng không còn
phải gánh vai trò chứng minh đường đặt lệnh đúng.

**Quy tắc dự phòng domain phải tôn trọng:** `.com` là chính; `.pro` **chỉ**
dùng khi lỗi mạng (DNS/TCP/TLS/timeout). Nếu `.com` trả về HTTP kèm JSON hợp
lệ — kể cả `code != 0` — thì **không được** thử lại `.pro`. Đây là lỗi rất dễ
mắc: gặp lỗi nghiệp vụ rồi đổi domain thử lại là tự nhân đôi lệnh.

---

## 3. GIỚI HẠN TẦN SUẤT — con số ràng buộc mọi kế hoạch thu thập dữ liệu

Hai chiều độc lập, vượt chiều nào cũng ra lỗi `100410`:

| Chiều | Phạm vi | Khoảng điển hình |
|---|---|---|
| Per-UID | mỗi tài khoản (chủ API key) | 1/s – 30/s |
| Per-IP | mỗi địa chỉ IP nguồn | 1/s – 3/s |

Endpoint nến — thứ quyết định việc đo chiến lược:

```
GET /openApi/swap/v3/quote/klines
Rate limit: 1/s per IP.          limit: mặc định 500, TỐI ĐA 1440
```

### Tính ra thời gian nạp lịch sử (1 IP, 1 nến/giây, 1440 nến/lần)

| Khung | 5 năm/1 mã | Số lệnh gọi | 1 mã | 100 mã |
|---|---:|---:|---:|---:|
| 1d | 1.825 nến | 2 | ~2 giây | ~3 phút |
| 1h | 43.800 nến | 31 | ~31 giây | ~52 phút |
| 5m | 525.600 nến | 365 | ~6 phút | **~10 giờ** |

**Hệ quả cho kế hoạch:** đo trên khung **1d và 1h là rẻ**, làm được trong một
buổi. Khung 5m đắt gấp mười lần — đừng bắt đầu từ đó. Đây là ngược với thị
trường VN, nơi ta có sẵn 5m trong `bars`.

### Điều dự án này đã có sẵn và dùng lại được ngay

Bài học 429 ngày 01/09 áp thẳng vào đây: backoff nhân đôi, **trần riêng 600 s
cho lỗi tần suất** (`f8e3392`), và tuyệt đối không gõ cửa dồn dập khi bị chặn.
Ở BingX giới hạn còn chặt hơn SSI (1/s per IP), nên đây không phải rủi ro mới
mà là rủi ro đã biết cách xử lý.

---

## 4. CÓ PLUGIN CLAUDE CODE CHÍNH THỨC — đổi cách giao việc cho agent

```
/plugin marketplace add BingX-API/api-ai-skills
/plugin install bingx-ai-skills
```

29 skill, mỗi phân khúc có `SKILL.md` + `api-reference.md` với đường dẫn
endpoint, tham số và giới hạn tần suất ghi sẵn từng dòng.

**Nghĩa là brief cho agent KHÔNG nên bảo nó tự mò API.** Bảo nó cài skill và
đọc `api-reference.md`. Ít sai, và tài liệu đi kèm sàn nên không lệch phiên
bản.

Cảnh báo cân bằng: đây là code do bên thứ ba viết, chạy trong máy dự án. Trước
khi cài nên đọc qua nội dung skill — nhất là các skill *giao dịch*
(`swap-trade`, `spot-trade`) chứ không chỉ skill đọc dữ liệu. Kho có cả những
skill mang tính chiến lược (`bingx-rsi-bottom-hunter`,
`bingx-dynamic-sl-tp`) — **không dùng chúng làm chiến lược giao dịch**: chúng
chưa qua phép đo nào của dự án này, và dự án này vừa mất một tuần để chứng
minh rằng một chiến lược nghe hợp lý vẫn có thể thua mua-và-giữ 666 tỷ.

---

## 5. Ba con số phải xác minh trước khi lập brief chi tiết

Chưa tra được trong đợt này, và chúng đổi hình dạng kế hoạch:

1. **Độ sâu lịch sử tối đa** của endpoint nến — 1440 là số nến **mỗi lần
   gọi**, không phải giới hạn quá khứ. Cần biết dữ liệu lùi được tới năm nào,
   vì kỳ ngoài mẫu cần ít nhất vài năm.
2. **Phí maker/taker và chu kỳ funding** của hợp đồng vĩnh cửu — cần cho mô
   hình phí trong backtest. Bỏ funding sẽ làm kết quả đẹp giả tạo với vị thế
   giữ lâu.
3. **Cỡ lệnh tối thiểu và bước giá** từng cặp — tương đương lô 100 của HOSE.

---

## 6. Điều bản khảo sát này KHÔNG đổi

Không chiến lược nào trong repo có lợi thế đo được (`711683a`, `14a5ff3`).
BingX có testnet tốt, API rõ ràng, tài liệu tử tế — nhưng những thứ đó giải
quyết vấn đề **kỹ thuật**, không giải quyết vấn đề **lợi thế**. Thứ tự vẫn
phải là đo trước, dựng sau.

Điểm khác biệt đáng mừng: dữ liệu 24/7 với khung 1h nạp trong một giờ cho 100
cặp nghĩa là **vòng lặp đo nhanh hơn hẳn** thị trường VN. Đó mới là lợi ích
thật của việc sang crypto — không phải vì crypto dễ thắng hơn.
