# Brief đợt 111 — BingX: kết nối có ký bằng API key, **chỉ đọc**

Ngày giao: 27/09/2026. Base: main `1202245`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push, không build hay restart container**.
**Đợt này không đặt, không huỷ, không sửa lệnh nào.** Phần đặt lệnh là đợt 112, và chỉ giao sau khi Claude đã audit xong đợt 111.

## 0. Bối cảnh và quyết định của chủ dự án

- **Hiện trạng:** repo chỉ gọi endpoint **công khai** của BingX (`scripts/bingx_klines.py`, `BASE_URL = https://open-api.bingx.com`). Chưa có ký request, chưa đọc được tài khoản, chưa đặt được lệnh.
- **Chiến lược:** chưa có chiến lược crypto nào có lợi thế đã đo. Cả bốn module A/B/C/D trong tài liệu của chủ dự án đều âm (đợt 37–38, 44, 105, 106).
- **Quyết định ngày 27/09:** chủ dự án vẫn muốn **chuẩn bị sẵn hạ tầng**. Làm theo đúng khuôn đường lệnh SSI:
  1. chỉ đọc (đợt này);
  2. diễn tập đặt rồi huỷ lệnh, do người vận hành tự bấm (đợt 112);
  3. **không** nối vào engine tự động. Việc nối engine chỉ làm khi có chiến lược có lợi thế.
- **Ràng buộc đứng của dự án:** **không đoán** endpoint, cách ký, bước khối lượng hay phí của BingX (memory `bingx-fee-schedule`). Mọi chi tiết API phải trích từ **tài liệu chính thức**, kèm URL, hoặc từ phản hồi thật của API.

## 1. Việc chủ dự án làm (không phải agent)

Tạo trên BingX **một API key chỉ bật quyền Read**. **Không** bật Trade, **không** bật Withdraw. Gắn IP whitelist nếu BingX cho phép.

Ghi key vào `.env` với hai biến `BINGX_API_KEY` và `BINGX_API_SECRET`. Không dán key vào chat, không commit.

Nếu agent làm lúc chủ dự án chưa có key: mọi test chạy bằng fake, còn bước 5 (thăm dò thật) ghi **"BỎ QUA — chưa có key"**. Đợt vẫn được coi là xong.

## 1b. Cập nhật 27/09: key đã có trong `.env`

Claude kiểm ngày 27/09, **chỉ đọc tên biến, không đọc giá trị**. `.env` đang có `BingX_API_KEY` (85 ký tự) và `BingX_API_SECRET` (82 ký tự).

Tên biến **viết hoa thường lẫn lộn**, khác quy ước của repo (`BINGX_API_KEY`, giống `SSI_*`). Trên Windows biến môi trường không phân biệt hoa thường, nhưng trên VPS Linux thì **có**.

Claude đã đề nghị chủ dự án đổi tên sang `BINGX_API_KEY` / `BINGX_API_SECRET`. Code **chỉ** đọc tên viết hoa. Không thêm nhánh đọc tên khác để "cho chạy được".

Nếu thiếu biến viết hoa, probe phải thoát với mã khác 0 và thông điệp nêu **đúng tên biến cần có**. **Không** in giá trị. Nếu đây là tình huống agent gặp, dán thông điệp đó rồi **dừng bước 5** để chủ dự án đổi tên. Agent **không tự sửa `.env`**.

**Kiểm quyền của key (thêm vào bước 5).** Nếu tài liệu chính thức có endpoint đọc quyền của API key, probe gọi nó và in danh sách quyền. Nếu key đang bật **Trade** hoặc **Withdraw**, probe in **CẢNH BÁO** và thoát với mã khác 0: key của đợt 111 phải là key **chỉ đọc**. Nếu tài liệu không có endpoint như vậy, ghi "không kiểm được quyền bằng API — chủ dự án tự xác nhận trên web BingX".

**Không tự suy ra định dạng key.** Độ dài 85/82 ký tự có thể khác độ dài chuẩn, ví dụ do dấu cách hay chú thích cuối dòng. Nếu xác thực thất bại, in mã lỗi và thông điệp của BingX, rồi báo lại. **Không** đoán nguyên nhân.

## 2. Phạm vi

| File | Được làm gì |
|---|---|
| `trading/bingx_client.py` | **Mới.** Client HTTP (dùng `requests` hoặc `httpx`, thư viện nào **đã có** trong `pyproject.toml` thì dùng; không thêm dependency). Gồm hàm ký request, và các phương thức đọc: số dư tài khoản perpetual, vị thế đang mở, lệnh đang chờ, thông số hợp đồng (bước giá, bước khối lượng, khối lượng tối thiểu), giá hiện tại. **Không có** phương thức đặt, huỷ hay sửa lệnh. |
| `tests/test_bingx_client.py` | **Mới.** |
| `scripts/bingx_account_probe.py` | **Mới.** Script chỉ đọc, chạy tay, in snapshot tài khoản (xem bước 5). |
| `.env.example` | Thêm `BINGX_API_KEY=`, `BINGX_API_SECRET=`, **để trống giá trị**. |
| `trading/crypto_fees.py` | **Chỉ đọc.** Nếu tài liệu chính thức cho thấy phí khác `0.0002 / 0.0005` thì báo lại, không sửa. |

**Không được đụng:**
- `trading/engine`, `trading/collector`, storage, schema DB;
- `docker-compose.yml`: chưa container nào cần key BingX, script chạy trên host;
- config, Task Scheduler.

Không tạo bảng DB mới. Không ghi DB.

## 3. Yêu cầu nội dung

1. **Nguồn.** Chỉ dùng tài liệu API chính thức của BingX. Với **mỗi** endpoint và **mỗi** chi tiết ký, ghi vào docstring URL tài liệu và mục trích ra. Các chi tiết ký gồm:
   - thuật toán;
   - chuỗi được ký là gì, thứ tự tham số;
   - `timestamp` và `recvWindow`;
   - tên header chứa key.

   Chỗ nào tài liệu mơ hồ thì ghi rõ, và chốt bằng **phản hồi thật** ở bước 5 (hoặc để "chưa xác minh" nếu chưa có key).
2. **Bí mật.**
   - `api_secret` **không bao giờ** xuất hiện trong log, alert, exception, `repr` hay chuỗi URL được log.
   - `api_key` chỉ được log dạng che, ví dụ 4 ký tự đầu + `…`.
   - Phải có test chứng minh điều này.
3. **Lỗi không được im lặng.** Các trường hợp sau đều ném ra ngoại lệ **rõ ràng**, có mã lỗi và thông điệp của BingX nhưng **không** kèm secret:
   - HTTP khác 200;
   - `code != 0` trong body;
   - timeout;
   - JSON hỏng.

   **Không** trả `None` hay `0` thay cho "không đọc được". Số dư bằng 0 và "không đọc được số dư" phải phân biệt được với nhau.
4. **Đồng hồ.** BingX từ chối request nếu `timestamp` lệch quá `recvWindow`, nên client phải kiểm được độ lệch giữa giờ máy và giờ server. Nếu tài liệu có endpoint giờ server công khai thì dùng nó, và probe in ra độ lệch.
5. **Chỉ đọc là ràng buộc cứng.** Test phải chứng minh client **không có** bất kỳ phương thức nào gửi request `POST`/`DELETE`/`PUT` tới endpoint lệnh. Làm bằng cách quét (AST hoặc introspection) các chuỗi endpoint và phương thức HTTP xuất hiện trong module.

## 4. Các bước

**GitNexus.** Đợt này chủ yếu tạo file mới. Chạy `npx gitnexus impact` cho symbol có sẵn nào bị sửa (dự kiến không có), và cuối đợt chạy `npx gitnexus detect-changes --scope all --repo AI_auto_trading_system`.

1. **Đọc tài liệu và lập bảng.** Bảng gồm các cột `Mục đích | Method | Path | Tham số | URL tài liệu`, một dòng cho mỗi endpoint dùng trong đợt. Thêm một đoạn mô tả cách ký, trích nguyên văn tài liệu.
   → **Kiểm chứng bằng:** bảng trong báo cáo. Claude sẽ tự mở từng URL để đối chiếu.

2. **Hàm ký (TDD).** Nếu tài liệu có **ví dụ ký mẫu** (key, secret, tham số → chữ ký), dùng đúng ví dụ đó làm test: chữ ký phải khớp **từng ký tự**. Nếu tài liệu không có ví dụ, tự tính HMAC tay trong test bằng `hmac` của thư viện chuẩn, và ghi rõ "không có vector chính thức".
   → **Kiểm chứng bằng:** pytest.

3. **Các phương thức đọc (TDD, dùng fake HTTP).** Viết test cho:
   - parse đúng phản hồi mẫu. Lấy mẫu từ tài liệu, hoặc từ phản hồi thật ở bước 5 sau khi đã che số liệu nhạy cảm.
   - bốn nhánh lỗi ở §3 mục 3;
   - không lộ secret;
   - khẳng định chỉ đọc (§3 mục 5).

   → **Kiểm chứng bằng:** pytest, toàn bộ xanh.

4. **Phá thử.** Mỗi phép phá phải làm ít nhất một test đỏ:
   - (i) đổi thứ tự tham số trong chuỗi ký;
   - (ii) cho `code != 0` trả về `None`;
   - (iii) đưa `api_secret` vào thông điệp lỗi.

   Sao lưu ra ngoài repo rồi khôi phục từ bản sao lưu. **Cấm `git checkout`, `git restore`, `git stash`.**
   → **Kiểm chứng bằng:** dán tên test đỏ cho từng phép phá, rồi dán lần chạy xanh sau khi khôi phục.

5. **Thăm dò thật, chỉ khi `.env` đã có key.**
   ```
   uv run python scripts/bingx_account_probe.py
   ```
   In ra:
   - độ lệch đồng hồ;
   - số dư USDT perpetual;
   - số vị thế đang mở;
   - số lệnh đang chờ;
   - thông số hợp đồng `BTC-USDT`: bước giá, bước khối lượng, khối lượng tối thiểu, và **nguồn** của từng số.

   Kèm thêm **một** lần gọi có chủ đích với chữ ký sai, để chứng minh client ném lỗi rõ ràng.
   → **Kiểm chứng bằng:** dán output. Số dư có thể che bớt nếu chủ dự án muốn, nhưng giữ đúng định dạng.

6. **Kiểm tra toàn cục:**
   - `uv run pytest -m "not integration" -q` (mốc 1134)
   - `uv run ruff check trading tests scripts/bingx_account_probe.py`
   - `detect-changes`

## 5. Báo cáo cho Claude

Báo cáo gồm các phần sau, theo thứ tự:
1. Kết luận ngắn.
2. Bảng endpoint kèm URL tài liệu.
3. Cách ký, trích nguyên văn tài liệu.
4. Output test đỏ rồi xanh.
5. Phá thử.
6. Output bước 5, hoặc "BỎ QUA — chưa có key".
7. Những chi tiết **chưa xác minh**.
8. Mọi chỗ tài liệu BingX khác với giả định trong repo, như phí và endpoint `bingx_klines.py` đang dùng.

Kết thúc bằng câu: "Tôi không commit, không push, không đặt/huỷ/sửa lệnh nào, không ghi DB, không in secret."
