# Brief đợt 164 — CONFIRM-1: không xác nhận "danh mục rỗng / số dư 0" ngoài giờ giao dịch

Ngày: 08/10/2026. Người giao, audit, commit, push: Claude. Người thực thi: agent khác, **KHÔNG commit, KHÔNG push**.

## 0. Vấn đề (Claude đã đo, không phải phỏng đoán)

Đợt 124 thêm CONFIRM-1 vào `trading/collector/account_sync.py`. Khi SSI đột ngột trả danh mục rỗng, hoặc cả ba trường số dư bằng 0, thì hoãn một nhịp (5 phút), và xác nhận nếu nhịp sau vẫn như vậy.

Log `logs/bars_closed.log` cho thấy SSI trả rỗng/0 **gần như mọi đêm, khoảng 01:40–01:52 giờ VN**. Trong 4 đêm có dữ liệu, 3 đêm có hiện tượng này:

| Đêm (giờ VN) | Diễn biến | Hậu quả |
|---|---|---|
| 30/09 01:40 → 01:45 | rỗng **hai nhịp liên tiếp**, 01:50 đủ lại 6 mã | CONFIRM-1 xác nhận rỗng → `account_nav_snapshot` 0434226 = **−39.959.000** lúc 01:45:16 |
| 01/10 01:44 | rỗng một nhịp | bị chặn đúng |
| 03/10 01:51 | rỗng một nhịp | bị chặn đúng |

Hai nhịp không đủ, vì đợt bảo trì của SSI có lúc dài hơn 5 phút. Trên VPS chạy 24/7, việc này sẽ xảy ra đều đặn.

**Cách sửa dựa trên một sự thật, không đoán khung giờ bảo trì:** danh mục chứng khoán chỉ đổi qua lệnh khớp **trong phiên**. Ngoài giờ giao dịch, chuyển từ "có cổ phiếu" sang "rỗng" là không thể có thật. Vì vậy chỉ được **xác nhận** khi nhịp xác nhận nằm trong cửa sổ ngày giao dịch. Ngoài cửa sổ thì giữ trạng thái chờ, không ghi.

Đợt 124 tôi đã chọn "không chặn theo giờ" vì khung lỗi của SSI không rõ. Quy tắc mới không phụ thuộc khung lỗi; tôi đổi lựa chọn đó vì dữ liệu ở bảng trên.

## 1. Quy tắc mới (chốt, không tự đổi)

- **Cửa sổ xác nhận:** ngày giao dịch theo `is_trading_day(d, cfg.holidays)` (`trading/calendar_vn.py`), giờ VN từ **09:00 tới 15:30**, tính cả hai đầu. Lấy tới 15:30 thay vì 14:45 để một lệnh bán khớp lúc ATC vẫn kịp được xác nhận ngay trong ngày.
- **Áp cho cả hai nhánh CONFIRM-1:** danh mục rỗng đột ngột (`_sync_positions`) và cả ba trường số dư = 0 đột ngột (`_sync_balance`).
- **Nhịp đầu phát hiện bất thường:** giữ nguyên hành vi hiện có (đặt cờ chờ, WARN, không ghi), dù trong hay ngoài cửa sổ.
- **Nhịp tiếp theo vẫn rỗng/0:**
  - `ts` trong cửa sổ → xác nhận, ghi như hiện nay (giữ WARN xác nhận).
  - `ts` ngoài cửa sổ → **không ghi**, giữ cờ chờ, **không phát WARN mới** (tránh mỗi 5 phút một tin Telegram cả đêm). Có mức log thấp hơn WARN thì ghi một dòng ở mức đó; không có thì không ghi gì. Báo trong báo cáo đã chọn cách nào.
- **Nhịp trả lại dữ liệu bình thường:** xóa cờ chờ, ghi bình thường (như hiện nay).
- **Tài khoản vốn đã rỗng** (snapshot trước rỗng, ví dụ 0434221): ghi ngay ở mọi giờ (như hiện nay, SYNC-1).
- Giả định chấp nhận: chờ qua đêm rồi tới nhịp 09:00 đầu tiên vẫn rỗng thì xác nhận ngay ở nhịp đó, chỉ với một lần quan sát trong phiên. Lúc 09:00 SSI đã hết bảo trì nên chấp nhận được. Nếu agent thấy lý do khác thì báo, không tự đổi.

## 2. Phạm vi

- **Được sửa:** `trading/collector/account_sync.py`, chỉ `_sync_balance`, `_sync_positions` và lời gọi hai hàm này trong `sync_account_data`. Được thêm một hàm nhỏ kiểm cửa sổ trong cùng file. Truyền `cfg.holidays` xuống như `_sync_nav` đang làm.
- **Được sửa:** `tests/test_account_sync.py`.
- **Không sửa:** `trading/calendar_vn.py`, engine, storage, mức cảnh báo của các nhánh khác, mọi file khác. Thấy vấn đề ngoài phạm vi thì báo, không tự sửa.
- **Không** khởi động lại, không build lại container `collector`. Claude triển khai ngoài giờ phiên.
- GitNexus: chỉ mục đang cũ, chạy `npx gitnexus analyze` trước. Chạy `impact` cho `_sync_balance`, `_sync_positions`, `sync_account_data` (dán mức rủi ro). Chạy `detect_changes` sau khi xong.

### Test cũ phải đổi có chủ đích

`test_b2_sudden_empty_confirmed_on_second_sync` (`tests/test_account_sync.py:864`) dùng `ts = 23:18` và kỳ vọng xác nhận. Theo quy tắc mới, kỳ vọng đó sai.
- Chuyển `ts` của b2 vào trong phiên (ví dụ 10:00 một ngày giao dịch) để giữ ý nghĩa "trong phiên, hai nhịp thì xác nhận".
- Thêm test mới cho ban đêm (mục 3, test 1).
- Rà mọi test CONFIRM-1 khác dùng giờ ngoài cửa sổ. Liệt kê từng test đã đổi `ts`, kèm lý do; không đổi kỳ vọng nào khác.

## 3. Kiểm chứng: TDD, viết test trước, thấy đỏ rồi mới sửa code

1. **Tái hiện 30/09 (danh mục):** snapshot trước có 6 mã. Nhịp 01:40 rỗng → không ghi; nhịp 01:45 rỗng → **vẫn không ghi**, không có WARN mới; nhịp 01:50 đủ 6 mã → ghi 6 mã, cờ chờ đã xóa. Trên code hiện tại, test này phải đỏ ở nhịp 01:45.
2. **Tái hiện 30/09 (số dư):** như test 1, cho nhánh cả ba trường = 0.
3. **Trong phiên:** 10:00 rỗng, 10:05 rỗng → ghi rỗng ở 10:05 (đây là b2 đã dời giờ).
4. **Biên cửa sổ:** chờ từ 15:25. Nhịp 15:30 rỗng thì xác nhận. Lặp lại kịch bản với chờ từ 15:30 và nhịp 15:35 rỗng thì không xác nhận.
5. **Ngày nghỉ:** ngày lễ trong `holidays`, rơi vào thứ Ba, lúc 10:00, hai nhịp rỗng → không ghi. Thứ Bảy 10:00 → không ghi.
6. **Qua đêm:** chờ từ 01:40, các nhịp đêm vẫn rỗng (không ghi), nhịp 09:00 ngày giao dịch vẫn rỗng → ghi.
7. **Tài khoản vốn rỗng:** snapshot trước rỗng, nhịp 01:45 rỗng → ghi ngay (SYNC-1 giữ nguyên).
8. **Số dư một trường = 0** (b7, tài khoản margin): vẫn ghi bình thường ở mọi giờ.

Kiểm thử phá hoại: sao lưu file ra ngoài repo trước khi phá; cấm `git checkout/restore/stash`. Mỗi bước báo tên test đỏ.
- Bỏ điều kiện cửa sổ (luôn xác nhận) → test 1 và 2 đỏ.
- Đổi 15:30 thành 14:45 → test 4 đỏ.
- Bỏ kiểm ngày giao dịch (chỉ xét giờ) → test 5 đỏ.
- Xóa cờ chờ khi nhịp ngoài cửa sổ vẫn rỗng → test 6 đỏ.

```
uv run pytest tests/test_account_sync.py -v
uv run pytest -m "not integration" -q
uv run ruff check trading tests
```

**Hoàn thành khi:**
- 8 test mới/sửa đều xanh, bốn bước phá hoại mỗi bước làm đỏ đúng test đã nêu.
- Bộ đầy đủ không có test mới đỏ. Mốc 08/10: `1753 passed, 150 deselected`; dán số trước và sau.
- ruff sạch.
- `detect_changes` chỉ gồm hai file trên, cộng các dòng thống kê GitNexus nếu `analyze` tự sửa `AGENTS.md`/`CLAUDE.md`.

## 4. Báo cáo cho Claude
1. Kết quả `impact` của ba hàm, kèm mức rủi ro.
2. Danh sách test cũ đã đổi `ts`, kèm lý do.
3. Output pytest/ruff và bảng bốn bước phá hoại.
4. Output `detect_changes`.
5. Cách xử lý log ở nhịp ngoài cửa sổ (mức log nào, hay không ghi).
6. Mọi chỗ phải tự diễn giải; không im lặng chọn.

## 5. Việc Claude làm sau khi duyệt
- Commit, push. Build lại `collector` **ngoài giờ phiên** (sau 15:00, trước 01:30).
- Kiểm hai đêm kế tiếp, khung **00:00–03:00**. Không lấy khung hẹp hơn: đợt 124 từng kết luận sai vì nhìn khung quá hẹp.
  - Mục tiêu: `account_nav_snapshot` có `nav <= 0` = 0 dòng.
  - Mỗi đêm có SSI lỗi thì chỉ có **một** WARN CONFIRM-1 cho mỗi tài khoản.
