# Brief đợt 190: nạp dữ liệu giao dịch khối ngoại theo ngày (SSI DailyStockPrice) vào DB

- Người lập: Claude (planner), 23/10/2026. Agent thực thi: viết code + test, **không commit, không push**.
- Bối cảnh: chủ dự án chọn hướng B, tức khám phá chiến lược từ nguồn thông tin **khác giá/khối lượng**. Đã có 23 phép đo âm, tất cả đều chỉ dùng giá và khối lượng (đợt 188 là phép thứ 23).
- Đây là việc **hạ tầng dữ liệu**, không phải giả thuyết, nên không tốn ngân sách giả thuyết.
- Phép khám phá sẽ là **brief 191**, mở từ 01/11, có dòng H trong spec và hàng rào như đợt 188. Agent **không** làm phân tích hay chiến lược nào trong brief này.

## 0. Sự thật đã đo (Claude gọi API thật, chỉ đọc, 23/10)

1. **Endpoint:** `ssi_fc_data` → `MarketDataClient.daily_stock_price(None, model.daily_stock_price(symbol, fromDate, toDate, pageIndex, pageSize, market))`, gọi `GET Market/DailyStockPrice`.
   - Ngày ở dạng `dd/MM/yyyy`.
   - SDK mới `ssi_sdk` **không có** trường khối ngoại. Brief này vì vậy dùng `ssi_fc_data` (đã cài: `ssi_fc_data-2.2.2`). Client tạo theo mẫu `SSIRestClientLegacy` trong `trading/collector/backfill.py`, gồm `_SdkCfg` với `consumerID` và `consumerSecret` lấy từ `Config`.
2. **Token:** `MarketDataClient._get_access_token` tự lấy token mới khi còn dưới 1 giờ là hết hạn, không cần OTP.
   - `requests.get` trong SDK **không đặt timeout**. Script phải **chạy tiếp được từ ngày cuối đã nạp** (§3.3), không sửa SDK.
3. **Lịch sử bắt đầu 26/02/2020.** VCB tháng 01/2020 trả `NoDataFound`; tháng 02/2020 chỉ có các ngày 26–28. HOSE và HNX cùng có dữ liệu từ 2021 (đã thử HPG, SHS). Ngày có `toDate` ở tương lai thì trả 0 dòng.
4. **Gọi cả sàn một lần:** `symbol=""`, `market` thuộc `HOSE`/`HNX`/`UPCOM`, `fromDate = toDate = một ngày`, `pageSize=1000`.
   - Ngày 22/10/2026: `totalRecord` HOSE 2.645, HNX 1.044, UPCOM 1.152. `pageSize` 1.000 được tôn trọng, nên HOSE cần 3 trang, HNX và UPCOM mỗi sàn 2 trang.
   - Kết quả có lẫn chứng quyền, trái phiếu và **mã rác** (`0.8536:`, `02006052`…). **Phải lọc** theo `symbol_universe` trong DB.
5. **Kiểu dữ liệu:**
   - Mọi giá trị số là **chuỗi** (`"175731"`, `"-310798"`); `Time` là `null`.
   - Trên 2.645 dòng HOSE ngày 22/10: `NetBuySellVol = ForeignBuyVolTotal − ForeignSellVolTotal` và `NetBuySellVal = ForeignBuyValTotal − ForeignSellValTotal` đúng ở **cả 2.645 dòng**.
6. **Fixture nguyên văn:** `tests/fixtures/ssi_daily_stock_price.json`, gồm 3 dòng thật (E1VFVN30, HPG, VCB, ngày 22/10/2026).

**Ngoài phạm vi:** BCTC và sự kiện doanh nghiệp. SSI FastConnect Data không có endpoint cho chúng, và chưa có nguồn nào đã kiểm điều khoản. Không thêm nguồn nào khác.

## 1. Thiết kế (đã chốt)

**Bảng mới** trong `trading/storage/schema.sql`. Bảng thường, không dùng hypertable: khoảng 1.600 mã × 1.650 ngày ≈ 2,6 triệu dòng, nhỏ.

```sql
CREATE TABLE IF NOT EXISTS foreign_flow_daily (
  symbol text NOT NULL,
  trading_date date NOT NULL,
  buy_vol bigint NOT NULL,
  sell_vol bigint NOT NULL,
  buy_val double precision NOT NULL,
  sell_val double precision NOT NULL,
  net_vol bigint NOT NULL,
  net_val double precision NOT NULL,
  current_room bigint,          -- ForeignCurrentRoom; NULL nếu API trả rỗng
  close_price double precision, -- ClosePrice, chỉ để đối chiếu với bars_daily
  ingested_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, trading_date)
);
```

**Ánh xạ trường** (đúng tên API): `ForeignBuyVolTotal`→`buy_vol`, `ForeignSellVolTotal`→`sell_vol`, `ForeignBuyValTotal`→`buy_val`, `ForeignSellValTotal`→`sell_val`, `NetBuySellVol`→`net_vol`, `NetBuySellVal`→`net_val`, `ForeignCurrentRoom`→`current_room`, `ClosePrice`→`close_price`, `TradingDate`→`trading_date`, `Symbol`→`symbol`.

**Quy tắc:**
- Lưu `net_*` **đúng như API trả**, không tự tính lại.
- Dòng có `net` khác `buy − sell` vẫn lưu, nhưng phải **đếm** và in ra (§3.3).
- Dòng thiếu trường hoặc có giá trị không phải số thì **không lưu**, cũng phải đếm và in.
- Ghi bằng upsert (`ON CONFLICT (symbol, trading_date) DO UPDATE`), nên chạy lại cùng một ngày không nhân đôi dữ liệu.
- **Không có lệnh DELETE hay TRUNCATE nào.**

## 2. Phạm vi file

**Được tạo hoặc sửa:**
- `trading/collector/foreign_flow.py` (mới), gồm:
  - `@dataclass(frozen=True) ForeignFlow` với các trường như bảng §1;
  - `parse_daily_stock_price(resp: dict, allowed: set[str]) -> tuple[list[ForeignFlow], dict[str, int]]`, trả các dòng hợp lệ và bộ đếm `{"rows", "kept", "not_in_universe", "bad_row", "net_mismatch"}`;
  - `fetch_day(client, d: date, markets=("HOSE","HNX","UPCOM"), page_size=1000, sleep=...) -> tuple[list[dict], dict]`, phân trang đến khi đủ `totalRecord`. `NoDataFound` nghĩa là không có phiên, không phải lỗi. Gặp `status` lạ thì thử lại **một lần**, lần hai vẫn lỗi thì `raise`.
- `trading/storage/schema.sql`: thêm bảng §1, dạng idempotent.
- `trading/storage/db.py`: thêm `write_foreign_flow(rows: list[ForeignFlow]) -> int` (upsert) và `read_foreign_flow(symbol, frm: date, to: date) -> list[ForeignFlow]`.
- `scripts/backfill_foreign_flow.py` (mới), CLI §3.3.
- Test mới: `tests/test_foreign_flow.py`, cùng một test integration trong `tests/test_storage.py`.

**Không được đụng:** `trading/collector/backfill.py` (chỉ đọc để học mẫu `_SdkCfg`), `trading/collector/main.py`, collector chạy hằng ngày, engine, `bars_daily`, SDK trong `.venv`.

**Ràng buộc:**
- Agent **không gọi API SSI thật**. Mọi test dùng client giả, đọc fixture hoặc dữ liệu tổng hợp.
- Agent **không chạy script backfill** trên DB thật. Claude sẽ chạy.
- Không mở `.env` hay `.ssi_sdk_token.json`, không in khoá.
- Không restart container, không chạy `scripts/sched.sh`.
- Không đưa job hằng ngày vào collector; việc đó để brief sau.

## 3. Các bước (TDD)

### 3.1 Parser → kiểm chứng bằng test xanh
1. Fixture, với `allowed = {"VCB","HPG"}`:
   - giữ 2 dòng, `not_in_universe = 1` (E1VFVN30);
   - VCB có `net_vol == -310798`, `buy_val == 9944021500.0`, `trading_date == date(2026,10,22)`.
2. Chép một dòng fixture, đổi `Symbol` thành `"0.8536:"`: dòng bị loại vì không thuộc universe.
3. Dòng có `ForeignBuyVolTotal = ""` hoặc `None`: `bad_row` tăng 1, dòng không được lưu.
4. Dòng tổng hợp có `NetBuySellVol` lệch `buy − sell`: vẫn giữ, `net_mismatch` tăng 1.
5. Dòng tổng hợp có `TradingDate = "03/04/2026"` phải cho ra `date(2026,4,3)` (ngày 3 tháng 4), tức không được đảo ngày và tháng.

### 3.2 `fetch_day` với client giả → kiểm chứng bằng test xanh
- Client giả có `totalRecord = 2645` cho HOSE, trả 1.000/1.000/645 dòng: tổng phải là 2.645, và **trang 3 phải được gọi**.
- `NoDataFound` ở cả 3 sàn: trả danh sách rỗng, không `raise`.
- `status` lỗi một lần rồi thành công: kết quả đủ. Lỗi hai lần liên tiếp: `raise`.
- Tham số `sleep` truyền vào được, để test không phải ngủ thật.

### 3.3 Script `scripts/backfill_foreign_flow.py`
- **Tham số:** `--config config/config.yaml`, `--from YYYY-MM-DD` (mặc định `2020-02-26`), `--to YYYY-MM-DD` (mặc định hôm qua), `--sleep 1.1`.
- **Vòng lặp:**
  - Duyệt từng ngày thứ Hai đến thứ Sáu.
  - Mỗi ngày gọi `fetch_day`, rồi `parse_daily_stock_price`; `allowed` lấy từ `symbol_universe` trong DB, đọc một lần.
  - Ghi bằng `write_foreign_flow` **sau khi xong từng ngày**. Mỗi ngày là một đơn vị nạp lại được.
  - In một dòng mỗi ngày: `YYYY-MM-DD rows=… kept=… not_in_universe=… bad_row=… net_mismatch=…`, hoặc `YYYY-MM-DD no_session`.
- **Cuối chạy:** in tổng các bộ đếm và ngày cuối đã ghi.
- **Mã thoát:**
  - 0: xong.
  - 2: lỗi API sau khi đã thử lại. In `last_done=<ngày>` để chạy tiếp với `--from <ngày sau>`.
  - 3: `symbol_universe` rỗng.
- **Test:**
  - `main()` chạy với client giả và storage giả trên 3 ngày (một ngày `NoDataFound`): mã thoát 0, storage nhận đúng 2 ngày dữ liệu.
  - Client giả lỗi ở ngày thứ 2: mã thoát 2 và in `last_done` bằng ngày 1. Đây là test đầu-cuối bắt buộc (bài học đợt 182, khi `main()` rỗng mà test vẫn xanh).

### 3.4 Storage (integration, `@pytest.mark.integration`, DB `trading_test`)
- `write_foreign_flow` hai lần cùng dữ liệu thì số dòng không đổi. Lần hai có `net_val` khác thì giá trị được cập nhật.
- `read_foreign_flow` trả đúng khoảng ngày, sắp theo ngày tăng dần.
- `init_schema` chạy hai lần không lỗi.

### 3.5 Phép phá
Mỗi phép phá phải làm đỏ ít nhất một test **gọi code sản phẩm**. Test chỉ so hằng số viết trong test thì không tính (lỗi của đợt 188). Phá xong khôi phục, rồi ghi lệnh và kết quả vào báo cáo.
- (a) `fetch_day` chỉ lấy trang 1.
- (b) Bỏ lọc universe.
- (c) Đảo `buy_vol` và `sell_vol` khi ánh xạ.
- (d) Đọc ngày theo `MM/dd/yyyy`.
- (e) `write_foreign_flow` dùng INSERT thường, không có `ON CONFLICT`.
- (f) `main()` không ghi gì, hoặc nuốt lỗi rồi trả 0.

Không có cờ phá thử trong code sản phẩm.

### 3.6 Toàn suite
- `uv run pytest -m "not integration" -q`: không đỏ thêm so với trước khi bắt đầu. Ghi số passed trước và sau.
- `uv run ruff check trading tests scripts/backfill_foreign_flow.py` sạch.

## 4. GitNexus (bắt buộc)
- **Trước khi sửa:** chạy `node .gitnexus/run.cjs context "Storage" --repo .` và `impact` cho `init_schema`. Dùng `gitnexus` hoặc `node .gitnexus/run.cjs`, **không dùng npx**.
- **Sau khi sửa:** chạy `detect-changes --scope all` và dán nguyên văn phần tóm tắt.
- HIGH/CRITICAL thì báo trong báo cáo. UNKNOWN thì grep xác nhận.

## 5. Báo cáo agent phải nộp
1. Nguyên văn kết quả GitNexus trước và sau khi sửa.
2. Diff tóm tắt theo file. Mọi dòng thay đổi phải truy ngược được về §2.
3. Danh sách test mới, số passed trước/sau, bảng phép phá (a)–(f) kèm test bị đỏ.
4. Chỗ mơ hồ đã gặp. Nếu có lựa chọn ảnh hưởng dữ liệu mà brief chưa quy định, **dừng và hỏi**.
5. Cam kết: không gọi API thật, không ghi DB thật, không chạy backfill, không commit/push.

## 6. Claude làm sau khi nhận báo cáo
1. **Audit:** đối chiếu diff với §2; chạy lại test và (a)–(f); grep trong file mới để chắc không có DELETE/TRUNCATE.
2. **Chạy thử một ngày** trên DB thật: `--from 2026-10-22 --to 2026-10-22`. Đối chiếu VCB với fixture, và `close_price` với `bars_daily`.
3. **Chạy toàn bộ** 26/02/2020 → hôm qua, khoảng 3,5 giờ, chỉ thêm dòng vào bảng mới. Ghi log vào `logs/backfill-foreign-flow-<ngày>.log`.
4. **Kiểm sau nạp:**
   - số phiên mỗi năm;
   - số mã mỗi phiên;
   - tổng `net_mismatch` và `bad_row`;
   - phiên nào số mã thấp bất thường.
5. Commit, push, cập nhật memory.
6. Từ 01/11: viết brief 191 (khám phá). Dùng lại khung đợt 188: chia mã theo băm, tách giai đoạn, sổ thử, cao nguyên, DSR, ≤ 3 ứng viên. Cổ phiếu từ 2024 trở đi là giai đoạn kiểm chứng. Dòng H và niêm phong viết **trước** khi agent thấy dữ liệu.
