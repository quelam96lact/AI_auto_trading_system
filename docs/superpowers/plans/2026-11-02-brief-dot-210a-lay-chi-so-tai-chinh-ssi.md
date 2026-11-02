# Brief đợt 210a: lấy bảng chỉ số tài chính SSI cho 150 mã (Researcher)

Ngày 02/11/2026. Người giao: Claude (Lead). Người làm: **Researcher**.
Đăng ký trước: spec mục H, dòng 02/11/2026, đợt 210.

## Mục tiêu

Chép **nguyên văn** bảng chỉ số tài chính của SSI cho đúng 150 mã trong `docs/research/dot210/universe.txt` (sha256 bắt đầu `75d558478aa374b7`) vào một file CSV. Việc này **chỉ lấy dữ liệu**: không tính toán, không xếp hạng, không đọc giá hay lợi nhuận cổ phiếu.

## Công cụ

Chỉ dùng `mcp__claude_ai_SSI_MCP__fundamental_list_financial_ratios`, mỗi mã gọi:

```
symbol=<mã>, orderBy=YearReport, order=ASC, pageSize=100, pageIndex=1
```

- Nếu nhận đủ 100 dòng thì gọi tiếp `pageIndex=2`, rồi tiếp tục cho tới khi nhận < 100 dòng.
- Lỗi hoặc kết quả rỗng: thử lại 1 lần. Vẫn lỗi thì ghi mã vào `missing.txt` kèm nguyên văn lỗi. **Không** tự điền số.

## Đầu ra (thư mục `data/research210/raw/`, bị gitignore, không commit)

**1. `ratios.csv`**, UTF-8, xuống dòng LF, có header đúng thứ tự:

```
symbol,year_report,length_report,roe,roa,debt_to_equity,gross_profit_margin,net_profit_margin,eps,book_value
```

- **Một dòng cho mỗi phần tử** mà tool trả về, kể cả dòng `year_report=0`, dòng không có chỉ số nào, và dòng `length_report` 6 hoặc 9.
- Giá trị **chép đúng từng ký tự** như chuỗi tool trả về, không làm tròn, không đổi định dạng.
- Field vắng thì để **trống**. Không ghi 0, không ghi `None`.
- Thứ tự dòng: theo mã (như `universe.txt`), trong mỗi mã giữ đúng thứ tự tool trả.

**2. `log.csv`**: `symbol,pages,rows,asOfUtc`. `asOfUtc` lấy từ `meta.asOfUtc` của trang 1.

**3. `missing.txt`**: các mã lỗi (có thể rỗng).

## Cách làm để không chép sai

- Làm theo lô, mỗi lô 10 mã: gọi tool, ghi ngay các dòng của lô vào file (append), rồi mới sang lô sau. Không giữ nhiều lô trong đầu.
- Sau mỗi lô, đếm số dòng đã ghi cho từng mã và so với số phần tử tool trả. Lệch thì ghi lại lô đó.
- Context gần đầy thì dừng ở ranh giới lô, báo Lead mã cuối đã xong. Lead sẽ cho làm tiếp.

## Cấm

- Gọi tool khác của SSI MCP, truy vấn DB, đọc `bars_daily` hay bất kỳ dữ liệu giá nào.
- Tính toán hay nhận xét về chỉ số ("mã này ROE cao", ...).
- Sửa file trong repo. Chỉ được ghi vào `data/research210/raw/`.
- Commit hoặc push.

## Báo cáo

- Số mã xong / 150, số dòng tổng của `ratios.csv`, nội dung `missing.txt`.
- 3 dòng đầu và 3 dòng cuối của `ratios.csv`.
- Xác nhận đã đếm khớp số dòng từng lô.

## Lead làm sau

- Lấy lại ngẫu nhiên 15 mã (10%) bằng chính tool đó và so **từng ký tự** với `ratios.csv`. Lệch một ô cũng làm lại lô chứa mã đó.
- Chạy Bước 0 của spec: tỷ lệ (mã, tháng) 2017–2022 có giá trị hợp lệ ≥ 60%. Không đạt thì dừng đợt 210.
