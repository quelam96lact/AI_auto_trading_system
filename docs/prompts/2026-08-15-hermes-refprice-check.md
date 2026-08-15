# NHIỆM VỤ: Chốt cơ chế (B) bằng GIÁ THAM CHIẾU, không cần lịch sự kiện bên ngoài

Repo: `D:\My_Vault_Obsidian\Project\AI_auto_trading_system`, nhánh `feature/data-layer`, base `bc983d3`.

Đọc trước: `docs/superpowers/research/2026-08-15-overnight-gap-causes.md` (kết quả việc
bạn vừa làm, đã chốt thành tài liệu).

## Ý tưởng — vì sao không cần đi tìm lịch GDKHQ

Bạn đề xuất lấy lịch sự kiện doanh nghiệp đối chiếu. Có đường rẻ hơn và **kiểm được
bằng chính API SSI đang dùng**, không phụ thuộc nguồn ngoài không xác minh được.

`ssi_sdk` có `get_securities_summary_historical` (xem
`.venv/Lib/site-packages/ssi_sdk/services/market_data.py`), model `SecuritiesSummary`
trả về `price_change` và `price_change_percent` bên cạnh OHLC.

`price_change` = close − **giá tham chiếu** của phiên đó. Suy ra:

```
refPrice(t) = close(t) − price_change(t)
```

Và đó chính là thứ trả lời câu hỏi còn lại:

- **refPrice(t) ≈ close(t−1)** → tham chiếu KHÔNG bị reset. Vậy một phiên đã nhảy +32%
  trong khi biên độ tối đa ±15% → dữ liệu nguồn thật sự sai, không phải sự kiện doanh nghiệp.
- **refPrice(t) ≠ close(t−1)** → tham chiếu ĐÃ bị reset giữa hai phiên → đúng là sự kiện
  đổi giá tham chiếu (GDKHQ / chia tách / chuyển sàn). Khi đó `refPrice(t) / close(t−1)`
  cho ra **đúng hệ số điều chỉnh**, và `price_change_percent` phải nằm trong biên độ sàn.

## Bước 0 — Kiểm khả thi TRƯỚC, đừng xây gì cả (quan trọng nhất)

Hai điều chưa ai kiểm, và nếu chúng sai thì cả nhiệm vụ này vô nghĩa:

1. **Endpoint có trả dữ liệu cho ngày cũ (2016–2018) không?** Nhiều endpoint SSI chỉ có
   dữ liệu gần đây.
2. **Response THÔ có thêm trường nào SDK đang vứt đi không?** `SecuritiesSummary.from_list`
   chỉ lấy một tập key cố định — nếu SSI trả cả `refPrice` / `ceiling` / `floor` thì SDK
   **đang bỏ qua chúng**, và ta lấy thẳng còn tốt hơn suy ra từ `price_change`.

→ Làm: gọi endpoint cho **đúng một mã, một khoảng ngày ngắn** (đề xuất `HNB` quanh
2016-03-31), in ra **JSON THÔ** của một dòng (trước khi parse thành model), rồi mới quyết
đi tiếp thế nào. Dán JSON thô đó vào báo cáo.

Nếu endpoint không có dữ liệu 2016 → thử với một sự kiện gần đây hơn (dùng
`scripts/research_gap_causes.csv`, lọc `cause = khong_giai_thich_duoc`, lấy ngày mới nhất).
Nếu vẫn không có → **DỪNG và báo "không kiểm được bằng đường này"**, đừng đi tìm nguồn
dữ liệu khác trên mạng.

## Bước 1 — Đối chiếu 10 mã đã biết

Dùng đúng 10 mẫu trong tài liệu research: HNB 2016-03-31, VNI 2016-05-30, VRG 2016-11-25,
HU4 2017-02-17, S12 2017-04-28, KSV 2017-08-23, TUG 2018-04-26, IPA 2018-06-13,
PTH 2018-10-08, VTA 2018-12-28.

Bảng kết quả phải có, mỗi mã một dòng:

```
mã | ngày | close(t-1) từ DB | refPrice(t) suy ra | tỉ lệ refPrice/close(t-1) |
     price_change_percent | kết luận: THAM CHIẾU RESET / KHÔNG RESET
```

**Lưu ý bẫy đơn vị — đã dính một lần rồi:** `bars_daily` chứa giá ĐÃ back-adjust (69% bar
có giá phân số), còn API rất có thể trả giá THÔ. **Đừng so trực tiếp hai con số tuyệt
đối.** So **TỈ LỆ** (`refPrice(t) / close(t−1)` với cả hai lấy từ CÙNG một nguồn), hoặc
lấy luôn `close(t−1)` từ chính API thay vì từ DB. Nói rõ trong báo cáo bạn đã chọn cách nào.

## Bước 2 — Kết luận

- Nếu ≥8/10 cho thấy **tham chiếu bị reset**: cơ chế (B) = sự kiện đổi giá tham chiếu.
  Ghi rõ hệ số điều chỉnh đo được của từng mã.
- Nếu ≥8/10 cho thấy **KHÔNG reset**: dữ liệu nguồn SSI sai thật (một phiên nhảy quá biên
  độ mà không có sự kiện nào) → cơ chế loại trừ hiện tại là cách duy nhất.
- Lẫn lộn → nói rõ tỉ lệ mỗi loại, không ép về một phía.

## Ràng buộc — giữ nguyên

- **CHỈ ĐỌC.** DB đang phục vụ `collector` + `engine` chạy live. Không
  `UPDATE`/`DELETE`/`INSERT` vào bảng hệ thống.
- Token đọc từ `ssi_auth_state`; hết hạn thì DỪNG và báo, không tự làm OTP.
- Không đụng `trading/engine/`, `trading/real_orders.py`, `scripts/confirm_real_order.py`,
  `config/config.yaml`. Phát hiện bug ở `trading/collector/` thì BÁO CÁO kèm test tái hiện,
  **đừng tự sửa** — code đang chạy production.
- KHÔNG commit, KHÔNG push.
- DSN `127.0.0.1`; script mới nhớ `sys.stdout.reconfigure(encoding="utf-8")`;
  `git diff --stat` sau mỗi Edit vì hook formatter reformat cả file.
- Nhớ đổi `ts` sang giờ HCM khi đọc `bars_daily` (`ts` lưu UTC — lệch một ngày là ra kết
  quả khác hẳn, đã dính một lần).

## Báo cáo cuối

1. JSON thô của một dòng response (Bước 0) + kết luận endpoint có dùng được cho ngày cũ không.
2. Bảng 10 mã như mô tả ở Bước 1, nói rõ đã xử lý bẫy đơn vị thế nào.
3. Kết luận Bước 2.
4. Output thật `pytest -m "not integration"` + ruff (8 lỗi pre-existing để nguyên).
5. Xác nhận không có câu lệnh ghi nào chạm bảng hệ thống.

Nếu Bước 0 cho thấy đường này không đi được thì DỪNG NGAY và báo — đó là kết quả hợp lệ,
tốn 15 phút thay vì nửa ngày. Đừng cố cứu nhiệm vụ bằng nguồn dữ liệu không xác minh được.
