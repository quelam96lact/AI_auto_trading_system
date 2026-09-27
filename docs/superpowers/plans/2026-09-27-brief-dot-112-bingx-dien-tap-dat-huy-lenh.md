# Brief đợt 112 — BingX: đường đặt/huỷ lệnh và script diễn tập (người vận hành tự bấm)

Ngày giao: **chỉ sau khi Claude đã audit và commit đợt 111.** Base: commit của đợt 111.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push**.
**Agent KHÔNG chạy `--send`.** Mọi lệnh thật do chủ dự án tự chạy, có Claude theo dõi.

## 0. Mục tiêu và giới hạn

Làm theo đúng khuôn diễn tập lệnh SSI (`scripts/drill_place_cancel_order.py`, đợt 100):
1. đặt **một** lệnh giới hạn nhỏ nhất có thể, ở giá **xa thị trường** để không khớp;
2. đọc lại trạng thái;
3. huỷ;
4. xác nhận đã huỷ.

Mục tiêu là chứng minh đường lệnh đúng từ đầu đến cuối, với rủi ro gần như bằng 0.

**Không làm:**
- nối vào engine hay chiến lược;
- lệnh market;
- đổi đòn bẩy hoặc chế độ ký quỹ;
- đóng hay mở vị thế thật;
- lịch tự động.

Chưa có chiến lược crypto có lợi thế, nên không có gì tự động gửi lệnh.

## 1. Key: MỘT key cho cả đọc lẫn đặt lệnh (chủ dự án quyết 27/09)

Key trong `.env` là `BINGX_API_KEY` / `BINGX_API_SECRET`. Theo xác nhận của chủ dự án:
- key **có quyền Trade**;
- **đã tắt Withdraw**;
- **đã gắn IP whitelist**.

Chủ dự án **chọn dùng một key** thay vì tách hai key như bản đầu của brief này. **Không** tạo biến `BINGX_TRADE_*`.

Vì không còn lớp bảo vệ phía sàn, việc tách quyền **dồn hết vào code** và phải được test ghim:
- `BingXClient` (đợt 111) giữ nguyên, **chỉ đọc**. Test "chỉ đọc" của đợt 111 vẫn phải xanh.
- Lớp đặt lệnh `BingXTradeClient` là lớp **riêng**, cũng đọc `BINGX_API_KEY` / `BINGX_API_SECRET`. Nó **chỉ** được khởi tạo trong `scripts/bingx_drill_place_cancel.py`.
- Thêm test quét toàn repo (AST hoặc grep có kiểm soát): ngoài file script diễn tập và test của nó, **không** file nào trong `trading/` hay `scripts/` import hoặc khởi tạo `BingXTradeClient`. Bất kỳ ai nối lớp này vào engine sau này sẽ làm test đỏ.
- Runbook phải ghi: **đổi máy chạy (ví dụ chuyển sang VPS) thì phải cập nhật IP whitelist trên BingX**. Nếu không, mọi request có ký sẽ bị từ chối.

## 2. Phạm vi

| File | Được làm gì |
|---|---|
| `trading/bingx_client.py` | Thêm một lớp **riêng** cho lệnh, `BingXTradeClient`, đọc cùng cặp `BINGX_API_*` (§1), gồm: đặt lệnh giới hạn, huỷ lệnh, đọc một lệnh theo id. Lớp chỉ đọc của đợt 111 **giữ nguyên**: test "chỉ đọc" của đợt 111 vẫn phải xanh với lớp đó. |
| `scripts/bingx_drill_place_cancel.py` | **Mới.** Script diễn tập (xem §3). |
| `tests/test_bingx_client.py`, `tests/test_bingx_drill.py` | Thêm và tạo mới. |
| `docs/superpowers/runbooks/dien-tap-lenh-bingx.md` | **Mới.** Runbook cho chủ dự án, cùng khuôn `dien-tap-lenh-that.md`. |

**Không được đụng:** engine, collector, storage, config, `docker-compose.yml`, Task Scheduler.

## 3. Hành vi bắt buộc của script diễn tập

Mọi chi tiết API phải trích từ tài liệu chính thức, kèm URL. Các chi tiết đó gồm:
- endpoint đặt, huỷ và đọc lệnh;
- tên tham số `side`, `positionSide`, `type`, `timeInForce`;
- cờ **post-only** nếu BingX có;
- danh sách trạng thái lệnh;
- môi trường demo.

**Không đoán.**

1. **Môi trường.**
   - Nếu tài liệu chính thức có môi trường **demo/giao dịch ảo** cho perpetual (tên miền hoặc cờ riêng), thì thêm `--env demo|live` với **mặc định `demo`**.
   - Nếu không có môi trường demo thì chỉ có live, và ghi rõ trong báo cáo.
2. **Mặc định là chạy khô.** Không có `--send` thì script in ra kế hoạch lệnh rồi thoát, **không** gửi gì. Kế hoạch gồm: môi trường, mã, chiều, giá, khối lượng, giá trị danh nghĩa, ký quỹ ước tính, giá thị trường tham chiếu, và khoảng cách % tới giá thị trường.
3. **Chỉ gửi khi đủ cả ba điều kiện:** có `--send`, người vận hành gõ **chính xác** `YES`, và (với live) có `--env live` tường minh.
4. **Mức lệnh:**
   - mã mặc định `BTC-USDT`;
   - chiều BUY;
   - khối lượng = **khối lượng tối thiểu** của hợp đồng, đọc từ API thông số hợp đồng;
   - giá = giá thị trường × **(1 − 5%)**, làm tròn **xuống** theo bước giá;
   - bật **post-only** nếu có. Nếu tài liệu không có post-only thì dùng lệnh giới hạn thường; giá cách 5% là lớp bảo vệ còn lại, và báo cáo phải ghi rõ điều này.
5. **Kiểm trước khi gửi.** Vi phạm bất kỳ điều nào thì thoát với mã khác 0 và thông điệp rõ:
   - độ lệch đồng hồ nằm trong ngưỡng an toàn so với `recvWindow`;
   - **không có** lệnh chờ nào trên mã đó;
   - **không có** vị thế mở trên mã đó;
   - số dư khả dụng ≥ 2 × ký quỹ ước tính;
   - giá trị danh nghĩa ≤ một trần cứng trong code (**20 USDT**).
6. **Sau khi gửi.** Theo đúng khuôn các nhánh của `drill_place_cancel_order.py` và cờ `send_attempted` của `confirm_real_order.py`:
   - Ngoại lệ **sau khi đã thử gửi**: alert CRITICAL, nói rõ **"KHÔNG RÕ LỆNH ĐÃ LÊN SÀN CHƯA — KIỂM TRA app BingX"**, exit 2.
   - Đọc lại lệnh tối đa 3 lần, có `sleep_fn` truyền vào được:
     - **đã khớp bất kỳ phần nào** → CRITICAL "ĐÃ KHỚP — ĐÓNG VỊ THẾ TAY TRÊN APP", **không** tự đóng, exit 2;
     - đang chờ → huỷ → đọc lại → phải là trạng thái "đã huỷ" → OK, exit 0;
     - huỷ thất bại → CRITICAL "LỆNH CÒN TREO — HUỶ TAY", exit 2;
     - không tìm thấy lệnh → exit 1 "ĐỐI CHIẾU TAY".
7. **Không lộ secret** ở bất kỳ nhánh nào, giống đợt 111.

## 4. Các bước

**GitNexus TRƯỚC khi sửa `bingx_client.py`.** Chạy `npx gitnexus impact <lớp/hàm đợt 111> --repo AI_auto_trading_system`. Cuối đợt chạy `detect-changes`.

1. **Bảng endpoint và trạng thái lệnh,** kèm URL tài liệu, cùng thể thức với đợt 111.
   → **Kiểm chứng bằng:** bảng trong báo cáo.
2. **TDD với fake HTTP.** Mỗi nhánh ở §3 mục 5 và mục 6 phải có ít nhất một test. Có thêm các test:
   - chạy khô không gửi request ghi nào (dùng spy);
   - gõ sai `YES` thì không gửi;
   - `live` mà thiếu `--env live` thì không gửi;
   - làm tròn giá xuống đúng bước giá;
   - khối lượng bằng khối lượng tối thiểu;
   - vượt trần 20 USDT thì dừng;
   - lớp chỉ đọc vẫn không có phương thức ghi.

   → **Kiểm chứng bằng:** pytest.
3. **Phá thử.** Mỗi phép phá phải làm ít nhất một test đỏ:
   - (i) làm tròn giá **lên**;
   - (ii) bỏ kiểm "không có lệnh chờ";
   - (iii) nhánh "đã khớp" trả exit 0;
   - (iv) cho lớp chỉ đọc gọi được endpoint đặt lệnh;
   - (v) import `BingXTradeClient` trong một file của `trading/engine` → test quét repo ở §1 phải đỏ.

   Sao lưu ra ngoài repo rồi khôi phục từ bản sao lưu. **Cấm `git checkout`, `git restore`, `git stash`.**
   → **Kiểm chứng bằng:** dán tên test đỏ cho từng phép phá, rồi dán lần chạy xanh sau khi khôi phục.
4. **Chạy khô thật.** Chỉ chạy nếu `.env` có key Read của đợt 111; chạy khô chỉ cần đọc. Dán nguyên văn kế hoạch lệnh.
   **Không `--send`.**
5. **Viết runbook `dien-tap-lenh-bingx.md`:**
   - key: một key Trade, tắt Withdraw, IP whitelist, và phải cập nhật whitelist khi đổi máy;
   - chạy khô;
   - chạy demo nếu có môi trường demo;
   - chạy live;
   - cần nhìn gì trên app BingX sau mỗi bước;
   - xử lý từng mã exit.
6. **Kiểm tra toàn cục:**
   - `uv run pytest -m "not integration" -q`
   - `uv run ruff check trading tests scripts/bingx_drill_place_cancel.py`

## 5. Báo cáo cho Claude

Báo cáo gồm các phần sau, theo thứ tự:
1. Kết luận ngắn.
2. Bảng endpoint và trạng thái lệnh kèm URL.
3. Có hay không có môi trường demo, dẫn nguồn.
4. Có hay không có post-only, dẫn nguồn.
5. Output test đỏ rồi xanh.
6. Phá thử.
7. Output chạy khô.
8. Những chi tiết chưa xác minh.

Kết thúc bằng câu: "Tôi không commit, không push, không chạy --send, không đặt/huỷ lệnh nào trên sàn."
