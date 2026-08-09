# SSI History Depth — Findings đo thật (Task 4)

**Ngày chạy:** 2026-08-09 (~20:55-21:05 VN)
**Nguồn:** `scripts/spike_ssi_history_depth.py` (dùng lại `SSIRestClient` +
`get_securities_info_by_board`), auth từ bảng `ssi_auth_state` (refresh token).

## Output nguyên văn

```
=== 1. So ma moi san ===
[san] HOSE: 767 ma | 5 dau: ['VNX50', 'VNCOND', 'VNFINLEAD', 'VNSI', 'VNXALLSHARE']
[san] HNX: 400 ma | 5 dau: ['HNXINDEX', 'HNX30', 'PXK', 'BCH', 'VIT']
[san] UPCOM: 862 ma | 5 dau: ['HNXUPCOMINDEX', 'FHH', 'VW1', 'DTR', 'TCP']
[san] da luu danh sach day du -> scripts/.spike_all_symbols.json

=== 2. Do sau daily (VCB) ===
[daily] lui 1 nam (2025-07): 22 bar
[daily] lui 2 nam (2024-07): 23 bar
[daily] lui 3 nam (2023-07): 23 bar
[daily] lui 5 nam (2021-07): 22 bar
[daily] lui 7 nam (2019-07): 21 bar
[daily] lui 10 nam (2016-07): 23 bar

=== 3. Do sau 5m (VCB, loc bo cac moc cuoi tuan/le) ===
[5m]    lui 110 ngay (2026-04-21): 46 bar
[5m]    lui 125 ngay (2026-04-06): 46 bar
[5m]    lui 128 ngay (2026-04-03): 46 bar
[5m]    lui 129 ngay (2026-04-02): 0 bar
[5m]    lui 130 ngay (2026-04-01): 0 bar
[5m]    lui 150 ngay (2026-03-12): 0 bar
[5m]    lui 180 ngay (2026-02-10): 0 bar
[5m]    lui 365 ngay (2025-08-09): 0 bar
```

Ghi chú đo: các mốc 0 bar do **cuối tuần/lễ** (11/04 thứ 7, 01/05 ngày lễ,
09/08/2025 thứ 7) đã bị loại khỏi bảng trên — chúng KHÔNG phải dấu hiệu hết
dữ liệu.

## Kết luận (con số chính xác, không "khoảng")

1. **Số mã mỗi sàn:** HOSE 767, HNX 400, UPCOM 862 — tổng **2.029 mã**.
   Lưu ý: mỗi sàn trả KÈM index (VNX50/VNCOND/VNSI... HNXINDEX/HNX30,
   HNXUPCOMINDEX) — cần lọc index trước khi backfill (xem mục Phát hiện).
2. **Daily lùi được ≥ 10 năm** — mốc xa nhất thử (2016-07) vẫn trả đủ 23 bar.
   Ngày sớm nhất đo được: **2016-07** (chưa đo tới giới hạn thật; đủ thỏa
   yêu cầu "~10 năm" của user).
3. **5m lùi tới 03/04/2026** — 128 ngày trước ngày chạy còn 46 bar, 129 ngày
   (02/04/2026) là 0 bar. **KHÔNG đạt 01/01/2026 như mục tiêu user.**
   ⇒ Task 7 chỉ backfill 5m được từ **03/04/2026** trở đi. Đây là kết quả hợp
   lệ (giới hạn API SSI), cần user điều chỉnh kỳ vọng.

## Phát hiện ngoài phạm vi (báo cáo, không sửa)

- Danh sách mã từ `get_securities_info_by_board` gồm cả **index** (~5-10 mã/
  sàn: VNX50, VNCOND, VNFINLEAD, VNSI, VNXALLSHARE, HNXINDEX, HNX30,
  HNXUPCOMINDEX...). Index không phải cổ phiếu — khi backfill (Task 5/7) nên
  lọc hoặc chấp nhận chúng trả 0 bar và đánh `error`/`skip`. Quyết định để
  Claude/user.
