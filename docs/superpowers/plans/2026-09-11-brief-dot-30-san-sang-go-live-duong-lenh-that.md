# Brief đợt 30 — Sẵn sàng go-live: đường lệnh thật chưa từng chạy trọn một vòng

Ngày giao: 10/09/2026, 18:45.
Base: `0a14be2` (main, cây sạch).
Người giao: Claude (planner/auditor).

**Thứ tự:** brief này chạy **sau** brief đợt 29 (bốn task của ngày 11/09). Task 1 và 4 ở đây
chỉ đọc DB nên làm song song lúc nào cũng được; Task 2 sửa code nên làm sau khi đợt 29 xong
để không trộn hai bản sửa vào một lần triển khai.

---

## 0. Điều tôi tìm ra khi khảo sát, và nó đổi cách nhìn về go-live

Tôi tra DB trực tiếp tối nay. Ba con số dưới đây quan trọng hơn mọi lỗi kỹ thuật còn lại.

### 0.1. Đường lệnh thật chưa từng khớp một lệnh nào

```
 pending_real_orders : 9 dòng
 real_order_fills    : 0 dòng
```

Cả 9 lệnh, không sót lệnh nào:

```
  id  | created_at (VN)      | account | symbol | side | qty | price | status  | ssi_order_id
 1218 | 2026-08-14 09:20:18  | 0434221 | IJC    | BUY  | 100 |  7700 | expired |
 1219 | 2026-08-14 09:21:36  | 0434221 | AAA    | BUY  | 100 |  7180 | expired |
 1220 | 2026-08-14 09:33:03  | 0434221 | HII    | BUY  | 100 |  8850 | expired |
 1221 | 2026-08-14 13:54:15  | 0434221 | IJC    | BUY  | 100 |  7430 | expired |
 1222 | 2026-08-14 13:57:32  | 0434221 | HII    | BUY  | 100 |  8660 | expired |
 1223 | 2026-08-19 13:42:21  | 0434221 | AAA    | BUY  | 100 |  6930 | expired |
 1224 | 2026-08-19 13:52:24  | 0434221 | IJC    | BUY  | 100 |  7210 | expired |
 1225 | 2026-08-19 13:59:42  | 0434221 | HII    | BUY  | 100 |  8680 | expired |
 1226 | 2026-09-04 09:20:17  | 0434221 | IJC    | BUY  | 100 |  7330 | expired |
```

**9/9 hết hạn. `ssi_order_id` rỗng hoàn toàn. `confirmed_at` rỗng hoàn toàn.**

Nghĩa là: engine **có** sinh đề nghị lệnh thật, nhưng chưa một lần nào đi qua được bước xác
nhận. Đường `pending → confirmed → placed → fill` **chưa từng chạy trọn một vòng**. Bảng
`real_order_fills` rỗng là bằng chứng cuối cùng.

Đây không phải lỗi. Cửa xác nhận thủ công là **thiết kế có chủ đích** (OTP là việc của chủ dự
án). Nhưng nó có nghĩa là **ta chưa biết đoạn đường đó có hoạt động hay không** — chưa từng
thử.

### 0.2. Tài khoản cấu hình không phải tài khoản có tiền

```
 account_no |    nav      | co vi the thuc te?
 0434221    |   5.021.712 | KHONG co dong nao trong account_position_snapshot
 0434226    | 197.517.988 | FOX 1.100 | HCM 1.000 | SSI 1.200 | TCX 160 | VCB 1.500
```

`config/config.yaml` đặt `real_order_account: "0434221"`. Cả 9 đề nghị lệnh đều nhắm vào tài
khoản đó. Log engine tối nay xác nhận: `"NAV lam real capital", "account": "0434221",
"nav": 5021712.0` — **toàn bộ sizing rủi ro thật đang dựa trên 5 triệu**, trong khi 197,5
triệu nằm ở tài khoản bên cạnh.

Chênh lệch **39 lần**. Đây là quyết định của chủ dự án, không phải lỗi để agent tự sửa — có
thể là cố ý (tài khoản nhỏ để thử nghiệm). Nhưng nó phải được **nói ra thành lời**, không phải
nằm im trong một dòng YAML.

### 0.3. Điều tôi tưởng là lỗi nhưng không phải

Tôi đã nghi lá chắn độ tươi vị thế sẽ chặn vĩnh viễn lệnh vào tài khoản rỗng, vì
`account_position_snapshot` không có dòng nào cho `0434221`. **Sai.**
`read_position_sync_ts()` (`storage/db.py`) đọc từ `account_sync_log`, không phải
`account_position_snapshot`, và bảng đó **có** dòng tươi cho cả hai tài khoản
(`2026-09-10 18:25:03`). Lá chắn `POSITION_MAX_AGE_MINUTES = 15` (đợt 10 Task 2) hoạt động
đúng. Ghi lại đây để không ai đi lại đường suy luận sai đó.

---

## 1. Bốn việc

| Task | Việc | Loại |
|---|---|---|
| 1 | Hồ sơ đường lệnh thật: vì sao 9/9 hết hạn | chỉ đọc, báo cáo |
| 2 | Lá chắn cấu hình tài khoản lệnh thật | sửa code + test |
| 3 | Runbook diễn tập lệnh thật đầu-cuối | soạn tài liệu |
| 4 | Bằng chứng ngày lễ và khoảng trống phía trước | chỉ đọc, báo cáo |

## 2. Ràng buộc

Giữ nguyên toàn bộ ràng buộc các đợt trước. Nhắc lại phần dễ quên:

- `real_trading_enabled` giữ `false`. **Không đổi.** Brief này chuẩn bị cho go-live, không
  thực hiện go-live.
- **Không gọi SSI, không gọi BingX.** Task 1 và 4 chỉ `SELECT` trên DB và đọc code.
- **Không gửi, không xác nhận, không huỷ bất kỳ lệnh thật nào.** Không đụng vào
  `pending_real_orders` — kể cả dòng `expired`.
- `config/config.yaml` **không sửa** (kể cả `real_order_account` và `holidays`).
- Không `TRUNCATE`/`DROP`/xoá dòng trên DB.
- Không `delete`/`purge`/`add`/`update` stream hay consumer NATS.
- Không xoá file. **Không commit, không push.**
- Mọi truy vấn có `ts` phải mở đầu bằng `SET TimeZone='Asia/Ho_Chi_Minh';`.
- Mọi `git diff` copy từ terminal. Mọi số liệu copy từ output thật.
- **Không bịa tiêu chí.** Đợt 29 trả về một bảng tiêu chí hoàn toàn khác brief, mô tả bar 1
  phút và phiên 09:15–14:45 — hệ thống này dùng bar 5 phút và phiên 09:00–15:00. Nếu thấy
  brief thiếu hoặc sai, **hỏi lại**, đừng tự thay bằng tiêu chí khác.

---

## Task 1 — Vì sao 9/9 đề nghị lệnh thật đều hết hạn

Chỉ đọc DB và đọc code. **Không chạy thử lệnh nào.**

Trả lời bằng số và bằng trích dẫn code có số dòng:

1. **Cửa sổ hết hạn là bao lâu?** Đọc `expires_at - created_at` của cả 9 dòng. Giá trị đó
   được đặt ở đâu trong code (file, dòng)? Có cấu hình được không?
2. **Ai phải làm gì để một lệnh chuyển từ `pending` sang `confirmed`?** Truy trong code toàn
   bộ đường đi: hàm nào đổi `status`, được gọi từ đâu, cần đầu vào gì (OTP? một script? một
   endpoint?). Nêu tên file và số dòng.
3. **Có công cụ nào để chủ dự án xác nhận không?** Nếu có, tên script và cách dùng. Nếu
   **không có** — nói thẳng "không có", đó là câu trả lời quan trọng nhất của task này.
4. **Phân bố thời điểm:** 9 lệnh rơi vào 3 ngày (14/08, 19/08, 04/09). Có phải chúng đến vào
   lúc chủ dự án khó thao tác không (giờ nào trong phiên)? Lập bảng.
5. `real_order_fills` rỗng — kiểm tra xem có đường code nào **từng** ghi vào bảng đó không,
   hay nó chưa bao giờ được đấu dây.

**Tiêu chí hoàn thành:** một người đọc báo cáo phải trả lời được câu *"muốn đặt một lệnh thật
ngày mai thì phải bấm gì, trong bao lâu"* mà không cần đọc code.

---

## Task 2 — Lá chắn cấu hình tài khoản lệnh thật

### 2.1. Vì sao

Hiện tại `real_order_account` là một chuỗi trong YAML mà **không gì kiểm tra nó có hợp lý
không**. Đặt nhầm số tài khoản thì hệ thống vẫn chạy êm, vẫn sinh đề nghị lệnh, vẫn tính
sizing — chỉ là dựa trên sai tài khoản. Đúng loại lỗi im lặng mà dự án này đã gặp nhiều lần
(engine câm vì đơn vị thanh khoản, chuông câm vì `load_config`, bar chưa đóng vì thiếu latch).

Ta không cần hệ thống **đoán** tài khoản nào đúng — đó là quyết định của chủ dự án. Ta cần nó
**nói ra** khi cấu hình trông đáng ngờ.

### 2.2. Việc cần làm

Trong `trading/real_orders.py`, ở nhánh đã có sẵn kiểm tra vị thế (quanh dòng 50-65), thêm
một cảnh báo **một lần khi khởi động** (không phải mỗi bar — tránh spam):

Khi tài khoản cấu hình có NAV **nhỏ hơn đáng kể** so với một tài khoản khác đã đồng bộ trong
`account_nav_snapshot`, phát `alert("WARN", ...)` nêu rõ: tài khoản đang cấu hình, NAV của
nó, tài khoản kia và NAV của tài khoản kia. **Không tự đổi tài khoản. Không chặn lệnh.**
Chỉ nói ra.

Ngưỡng: chênh **từ 10 lần trở lên**. Đặt thành hằng số có tên ở đầu file kèm một dòng chú
thích giải thích con số, theo đúng kiểu `POSITION_MAX_AGE_MINUTES` và
`BUYING_POWER_MAX_AGE_MINUTES` đang có.

**Chỉ sửa `trading/real_orders.py`.** Không sửa `trading/risk.py`, `PaperBroker`,
`trading/engine/main.py`, `config/config.yaml`.

Chạy `gitnexus_impact` trên `handle_crossover` trước khi sửa và báo cáo blast radius. Đây là
đường lệnh thật — **nếu impact trả về HIGH/CRITICAL, dừng và báo cáo trước khi sửa.**

### 2.3. Kiểm chứng

1. Test: tài khoản cấu hình NAV 5.021.712, tài khoản khác NAV 197.517.988 → **có** WARN, nội
   dung chứa cả hai số tài khoản và cả hai NAV.
2. Test: hai tài khoản NAV xấp xỉ nhau → **không** WARN.
3. Test: chỉ có đúng một tài khoản trong `account_nav_snapshot` → **không** WARN, không nổ.
4. Test: cảnh báo phát **một lần**, không lặp lại ở bar tiếp theo.
5. Test: có WARN nhưng lệnh **vẫn được xử lý bình thường** — lá chắn này chỉ nói, không chặn.
6. Suite đầy đủ pass, ruff sạch, cổng cứng VN khớp từng chữ số.

---

## Task 3 — Runbook diễn tập lệnh thật đầu-cuối

Viết `docs/superpowers/runbooks/dien-tap-lenh-that.md` (thư mục mới nếu chưa có).

Đây là **tài liệu cho chủ dự án tự thực hiện**, không phải việc agent chạy. Nội dung:

1. **Tiền đề cần đúng trước khi bắt đầu**: `real_trading_enabled`, `real_order_account`, số
   tiền tối thiểu, phiên giao dịch đang mở, container đang chạy. Mỗi mục kèm lệnh kiểm tra
   cụ thể và output mong đợi.
2. **Từng bước một**, đánh số: bật cái gì, chờ tín hiệu ở đâu, xác nhận bằng cách nào, trong
   bao lâu (dựa trên kết quả Task 1).
3. **Cách quan sát**: truy vấn SQL để xem `pending_real_orders` đổi trạng thái theo thời gian
   thực, và xem `real_order_fills` khi lệnh khớp.
4. **Cách huỷ giữa chừng** và cách quay về trạng thái an toàn (`real_trading_enabled: false`,
   dựng lại image vì config nung trong image — **ghi rõ điều này**, đây là cái bẫy đã suýt
   làm tôi restart nhầm tối 10/09).
5. **Dấu hiệu phải dừng ngay**: liệt kê cụ thể.
6. **Quy mô đề nghị cho lần diễn tập đầu**: một lệnh, một mã thanh khoản cao, khối lượng nhỏ
   nhất có thể. Nêu rõ con số.

**Không thực hiện runbook.** Chỉ viết.

---

## Task 4 — Ngày lễ: bằng chứng và khoảng trống phía trước

`config/config.yaml` hiện khai đúng ba ngày: `['2026-08-31', '2026-09-01', '2026-09-02']`.

Tôi đã dò dữ liệu, các ngày trong tuần **không có bar nào** trong `bars_daily` từ 03/04 đến
10/09:

```
 2026-04-27 | Mon
 2026-04-30 | Thu
 2026-05-01 | Fri
 2026-08-31 | Mon
 2026-09-01 | Tue
 2026-09-02 | Wed
```

Ba ngày đầu **chưa được khai** trong config.

Việc cần làm:

1. Xác nhận lại phép dò trên bằng truy vấn của chính agent (có ghim `TimeZone`), và kiểm tra
   chéo: ba ngày đó có bar trong bảng `bars` (5 phút) không? Nếu cả hai bảng đều rỗng thì
   kết luận vững.
2. **Nêu rõ giới hạn của phương pháp:** dò từ dữ liệu chỉ phát hiện được ngày lễ **đã qua**.
   Nó **không dự báo được** ngày lễ tương lai. Với go-live, thứ cần là danh sách **hướng về
   phía trước**.
3. Trả lời: từ 11/09/2026 tới hết năm, `holidays` trong config có ngày nào không? (Không —
   nêu ra thành lời.) Mốc cần khai tiếp theo là khi nào?
4. **Hậu quả cụ thể nếu thiếu:** đọc code và nói rõ ngày lễ chưa khai thì cái gì hỏng —
   `heartbeat_check` báo động giả cả ngày, hay engine làm gì đó sai? Trích dẫn số dòng.

**Không sửa `config/config.yaml`.** Danh sách ngày lễ chính thức là thông tin chủ dự án cung
cấp; agent chỉ đưa bằng chứng và nêu khoảng trống.

---

## 5. Báo cáo

Ngắn, đủ, đúng thứ tự. **Đừng dán toàn văn `git diff` và output dài** — dán con số và kết
luận. Task nào chưa làm ghi thẳng **"CHƯA LÀM"** kèm lý do.

1. Task 1: năm câu trả lời, mỗi câu kèm số dòng code hoặc số liệu DB. Kết lại bằng đúng một
   đoạn: *"muốn đặt một lệnh thật ngày mai thì phải bấm gì, trong bao lâu."*
2. Task 2: `gitnexus_impact` cho `handle_crossover`, `git diff --stat`, kết quả sáu tiêu chí.
3. Task 3: đường dẫn runbook + mục lục các bước.
4. Task 4: bảng ngày lễ đã kiểm chứng chéo, và trả lời bốn câu hỏi.
5. Ba dòng: số test pass, ruff, cổng cứng VN.
6. `git status --short`.

**Không commit, không push.**

---

## 6. Điều chỉ chủ dự án quyết được — và giờ đã có số

Brief này cố tình **không** đề xuất quyết định nào dưới đây. Nó chỉ làm cho chúng nhìn thấy
được.

| Câu hỏi | Số liệu đã có |
|---|---|
| **Q-1: có go-live không?** | VN: chiến lược −1.615.319.902 vs mua-và-giữ +1.897.587.481.903. Crypto 1h/30x: cả bốn chiến lược lỗ 15–21 USDT vs mua-và-giữ BTC +122,42 USDT. **Không chiến lược nào có edge đo được.** |
| **Q-2: giao dịch trên tài khoản nào?** | `0434221` NAV 5.021.712 (đang cấu hình) vs `0434226` NAV 197.517.988 + 5 vị thế thật. Chênh 39 lần. |
| **Q-3: đường xác nhận lệnh** | 9/9 đề nghị hết hạn, 0 lệnh từng khớp. Task 1 sẽ nói rõ vì sao. |
| **Q-5: ngày lễ** | 3 ngày đã qua chưa khai; danh sách tương lai trống. Task 4. |
| **Q-7: `risk_pct` cho 30x** | Đòn bẩy 30x đo được chỉ cho phơi nhiễm hiệu dụng 0,49–1,05x. Knob thật là `risk_pct`, không phải `leverage`. |
| Hạ tầng | Chuyển VPS; đăng ký scheduled task cho chuông 2C (**chờ đợt 29 Task 4 sửa báo động giả xong đã**); Docker autostart. |

Thấy thứ gì trong nhóm này chặn việc → **báo cáo, không tự quyết**.
