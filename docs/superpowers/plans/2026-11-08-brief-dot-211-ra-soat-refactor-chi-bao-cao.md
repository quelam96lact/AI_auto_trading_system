# Brief đợt 211: rà soát refactor (chỉ báo cáo, không sửa code)

Ngày 08/11/2026. Người giao: Claude (Lead). Người làm: **Builder**.

## Mục tiêu

Lập **danh sách ứng viên refactor** cho toàn repo để chủ dự án chọn. Đợt này **không sửa một dòng code nào**.

## Phạm vi đọc

- Được đọc: `trading/`, `scripts/` (bỏ qua file bắt đầu bằng dấu chấm), `tests/`, `docker-compose.yml`, `Dockerfile`.
- Không đọc: `data/`, `logs/`, `.env`, mọi file token hoặc khoá.
- Không truy vấn DB, không gọi API SSI, BingX hay DNSE, không chạy `sched.sh`, không chạy script đo.

## Công cụ

- Dùng GitNexus qua `gitnexus` hoặc `node .gitnexus/run.cjs`. **Không** dùng `npx`.
  - Index cũ thì chạy `node .gitnexus/run.cjs analyze --index-only` trước.
- Có thể dùng `query`, `context`, `impact` (upstream), `cypher`.
- Dead code: một symbol chỉ được ghi là "không ai gọi" khi **cả hai** điều sau đều đúng:
  - `impact` trả về không có caller;
  - `grep -rn "<tên>"` trên `trading scripts tests` cũng không có kết quả nào ngoài chính định nghĩa của nó.
  - Nếu `impact` trả `risk: UNKNOWN`, ghi rõ là UNKNOWN cùng kết quả grep.
- Được chạy `uv run ruff check`, `uv run pytest -m "not integration" -q`, và nếu đã cài sẵn thì `uv run vulture` (không cài thêm gói).

## Bốn nhóm cần tìm

1. **Code chết:**
   - hàm, lớp, hằng số trong `trading/` không còn ai dùng;
   - script trong `scripts/` không được tham chiếu ở `docker-compose.yml`, `trading/scheduler`, `scripts/*.sh`, test hay `DEPLOYMENT.md`.
   - Với script research đã đóng (`researchNNN_*`), chỉ ghi lại, không đề xuất xoá: chúng là bằng chứng của các phép đo đã công bố.
2. **Trùng lặp:** cùng một logic được viết ≥2 lần (ví dụ tính phí, RSI/ATR, bootstrap, loader bars, kết nối DB). Ghi rõ từng vị trí theo dạng `file:dòng` và mức độ giống nhau.
3. **File hoặc hàm quá lớn:** file > 800 dòng, hàm > 120 dòng trong `trading/` và các script đang chạy theo lịch.
4. **Rủi ro vận hành nằm trong code** mà một lần refactor sẽ sửa được: hằng số copy ở nhiều nơi, đường dẫn cứng, `localhost` thay vì `127.0.0.1`, cùng một ngưỡng nhưng hai giá trị khác nhau.

## Đầu ra

**Một file duy nhất:** `docs/audit/2026-11-08-ra-soat-refactor.md`. Mỗi ứng viên là một dòng trong bảng, gồm:

| # | Nhóm | Vị trí (`file:dòng`) | Mô tả | Bằng chứng (lệnh + kết quả rút gọn) | Blast radius (từ `impact`) | Lợi ích | Rủi ro | Ước lượng |

- Sắp xếp theo lợi ích/rủi ro, cao nhất lên đầu.
- Tối đa 30 dòng, chọn những dòng đáng làm nhất.
- Cuối file ghi số test pass hiện tại và kết quả ruff, để làm mốc trước refactor.

## Cấm

- Sửa, xoá hay đổi tên bất kỳ file nào ngoài `docs/audit/2026-11-08-ra-soat-refactor.md`.
- Commit, push.
- Ghi "không ai dùng" mà không có đủ cả hai bằng chứng `impact` và grep.

## Báo cáo cho Lead

- Đường dẫn file.
- Số ứng viên theo từng nhóm.
- Top 5.
- Số test pass.
