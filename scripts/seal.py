"""Mốc niêm phong (sealed timestamp) của dữ liệu crypto.

Tất cả dữ liệu bars_crypto có ts > CRYPTO_SEALED_MAX_TS là holdout và KHÔNG
được dùng trong bất kỳ phép đo nào. Script đo lường phải áp mốc này **vô điều
kiện** — tham số to_date của caller chỉ được thu hẹp thêm, không bao giờ mở
rộng quá mốc.

Giá trị: 2026-08-31 23:59:59+00 — tức hết ngày 31/08/2026 UTC.  bars_crypto.ts
là TIMESTAMPTZ lưu UTC (nguồn BingX epoch ms), nên so sánh trực tiếp.

Đợt 116/117/118 đã dùng hằng tương đương cho forex/BingX
(SEALED_MAX_TIMESTAMP_STR = "2026-08-31 23:59:59+00") nhưng khai báo cục bộ
trong từng script. Hợp nhất tất cả vào đây là nợ kỹ thuật ghi nhận, KHÔNG trả
trong đợt này.
"""

CRYPTO_SEALED_MAX_TS = "2026-08-31 23:59:59+00"
