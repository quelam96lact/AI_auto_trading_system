# Brief đợt 108 — Engine bỏ nến bẩn, và dọn 261 nến giá 0 trong `bars`

Ngày giao: 26/09/2026. Base: main `9d841d2`.
Người audit: Claude. Người thực thi: agent. Agent **không commit, không push, không build hay restart container, không DELETE trên DB thật**. Claude là người chạy lệnh xoá, sau khi audit.

## 0. Vấn đề (Claude đo 26/09)

- Bảng `bars` có **261 dòng OHLC = 0, volume = 0**, trên 6 mã (trong đó có HPG, IJC, AAA).
  - Tất cả nằm ở 09:00, 09:05, 09:10 (ATO) hoặc 14:30, 14:35, 14:40 (ATC).
  - Khoảng thời gian: 13/08 → 16/09.
  - Từ 17/09 không còn dòng nào như vậy, và cũng không còn nến ATO.
- Luật `is_dirty_bar` (`trading/data_quality.py:23`, một nguồn sự thật) mới chỉ được dùng trong các engine **backtest**. **Engine thật không lọc.** Toàn bộ `trading/engine` không gọi `is_dirty_bar` ở đâu.
- **Hệ quả đã thấy ở đợt 107:** ATR(14) đi qua các nến này bị thổi từ khoảng 20 lên khoảng 2.100. TP khôi phục của IJC/AAA ra khoảng +58% so với giá vốn, tức vô hiệu. EMA cũng bị kéo về 0 ở những nến đó.

## 1. Phạm vi

### Task A — Engine bỏ nến bẩn (code)

Một luật, áp ở **mọi** đường đưa bar vào chiến lược hoặc broker:

| Đường | Làm gì |
|---|---|
| Bar sống: `trading/engine/logic.py::process_bar` | Kiểm `is_dirty_bar(bar)` ngay **đầu** hàm, trước `broker.on_bar`. Nếu bẩn: không gọi broker, không cập nhật `marks`, không gọi strategy, trả `[]`. Phát **WARN một lần cho mỗi mã mỗi ngày**, dùng `day_state` theo khuôn `stop_blocked_alerted` đã có, nêu mã, `ts` và OHLC. |
| Warm-up (`main.py`, vòng `for hb in hist: strategy.compute_crossover(hb)`) | Bỏ các bar bẩn khỏi `hist` **trước** khi nạp. Nếu có bar bị bỏ, alert INFO nêu số bar bẩn đã bỏ. Nếu sau khi lọc còn ít hơn `warmup_bars` thì đi vào **đúng** nhánh WARN "thiếu lịch sử" đang có, không tạo nhánh mới. |
| Khôi phục TP (`main.py`, khối đợt 107) | Lọc bar bẩn khỏi `window` trước `restore_take_profit`. Nếu bar neo `A` là bar bẩn → WARN "không tái dựng được" (thêm lý do thứ tư) và **không** khôi phục. |

**Không** thêm điều kiện SQL lọc giá > 0 vào `storage`. Làm vậy tạo ra định nghĩa thứ hai của luật. Luật chỉ sống ở `data_quality.py`.

### Task B — Truy nguồn (chỉ đọc)

Vì sao nến giá 0 được ghi từ 13/08 đến 16/09 và ngừng từ 17/09? Trả lời bằng `git log` và code của collector (aggregator, grid phiên):
- commit nào,
- dòng nào đã tắt nguồn sinh nến 0,
- đường ghi hiện tại **còn** khả năng sinh bar giá 0 không (ví dụ ô 5 phút không có giao dịch).

**Chỉ báo cáo, không sửa collector.**

### Task C — Chuẩn bị dọn dữ liệu (agent chuẩn bị, Claude chạy)

1. **Sao lưu ra ngoài repo** vào `D:\My_Vault_Obsidian\Project\_backups\bars_zero_ohlc_20260926.csv`, bằng:
   ```
   \copy (SELECT * FROM bars WHERE open<=0 OR high<=0 OR low<=0 OR close<=0 ORDER BY symbol, ts) TO STDOUT WITH CSV HEADER
   ```
   `bars` có thể là hypertable. **Không** dùng `pg_dump -t` (bẫy đã gặp: ra file rỗng). Sau khi sao lưu, đếm số dòng trong file: **phải là 261** (không tính dòng tiêu đề).
2. Viết script SQL `D:\My_Vault_Obsidian\Project\_backups\delete_bars_zero_ohlc_20260926.sql`, **không chạy**. Script chạy trong một transaction:
   - đếm số dòng khớp điều kiện, dừng (`RAISE EXCEPTION`) nếu khác **261**;
   - `DELETE` theo đúng điều kiện của bước 1;
   - đếm lại, phải bằng 0;
   - `COMMIT`.
3. Kiểm bằng các `SELECT` sau, dán output:
   - phân bố 261 dòng theo mã và giờ;
   - `bars_daily` có dòng bẩn nào không (chỉ đếm, không đụng);
   - bảng nào khác đọc `bars` theo khung ATO/ATC mà việc xoá có thể ảnh hưởng. Grep `FROM bars`, rồi liệt kê.

**Agent tuyệt đối không chạy DELETE.**

**Không được đụng:**
- collector, `trailing_stop.py`, `paper_broker.py`, `real_orders.py`, `strategies/*`;
- storage (trừ khi test cần fake);
- config, `docker-compose.yml`, Task Scheduler.

Thấy lỗi ngoài phạm vi thì báo, không sửa.

## 2. Các bước

**GitNexus TRƯỚC khi sửa.** Chạy `gitnexus_impact` (upstream) cho `process_bar` và `run` trong `main.py`. MCP không kết nối được thì dùng CLI:
```
npx gitnexus impact process_bar --repo AI_auto_trading_system
```
Dán kết quả. Nếu HIGH hoặc CRITICAL thì **dừng lại và báo**. Cuối đợt chạy `npx gitnexus detect-changes --scope all --repo AI_auto_trading_system` và dán kết quả.

1. **Test `process_bar` (TDD, viết test đỏ trước):**
   - Bar bẩn: broker không nhận (lệnh chờ **không** khớp ở giá 0), `marks` không đổi, strategy không được gọi (dùng spy), trả `[]`.
   - Hai bar bẩn cùng mã trong cùng ngày → **một** WARN. Sang ngày mới → WARN lại.
   - Bar sạch ngay sau đó được xử lý bình thường.

   → **Kiểm chứng bằng:** pytest.

2. **Test warm-up và khôi phục TP** (theo khuôn integration trên `trading_test` của đợt 107):
   - Lịch sử có bar bẩn xen giữa → strategy không nhận bar bẩn, có INFO đếm số bar bỏ.
   - Cửa sổ khôi phục TP có bar bẩn → ATR khôi phục bằng ATR tính trên chuỗi đã lọc. So bằng `==` với một chiến lược "sống" chạy qua đúng chuỗi đã lọc; test này **phải đỏ** trên code cũ.
   - Bar neo `A` bẩn → WARN, `_tp` không được đặt.

   → **Kiểm chứng bằng:** pytest.

3. **Phá thử.** Sao lưu ra ngoài repo rồi khôi phục từ bản sao lưu. **Cấm `git checkout`, `git restore`, `git stash`.** Mỗi phép phá phải làm ít nhất một test đỏ:
   - (i) đặt kiểm bẩn **sau** `broker.on_bar`;
   - (ii) bỏ lọc ở cửa sổ khôi phục TP;
   - (iii) WARN phát ở **mọi** bar bẩn thay vì một lần mỗi ngày.

   Phép phá phải thật sự vi phạm luật.
   → **Kiểm chứng bằng:** dán tên test đỏ cho từng phép phá, rồi dán lần chạy xanh sau khi khôi phục.

4. **Chạy khô, chỉ đọc DB thật:** dùng lại script tạm của đợt 107 (ngoài repo), thêm bước lọc bar bẩn. In lại cho IJC và AAA: bar neo, số bar bẩn bị bỏ trong cửa sổ, `ATR_A`, TP khôi phục. In thêm giá đóng cửa gần nhất, và cờ **"SẼ BÁN NGAY KHI TRIỂN KHAI"** nếu TP ≤ giá đó.
   → **Kiểm chứng bằng:** dán output nguyên văn.

5. **Task B và Task C** theo §1.

6. **Kiểm tra toàn cục:**
   - `uv run pytest -m "not integration" -q` (mốc 1123)
   - `uv run pytest -m integration -q` (mốc 134)
   - `uv run ruff check trading tests`

## 3. Triển khai (Claude làm)

1. Audit xong thì commit.
2. **Sau 15:40 thứ Hai 28/09**, tức sau Lượt A của brief 104:
   - kiểm file sao lưu (261 dòng);
   - chạy script DELETE;
   - rebuild engine một lần, gộp cả đợt 107 và 108.
3. Sau khi engine khởi động lại, đọc log: INFO/WARN khôi phục TP của IJC/AAA phải khớp số của bước 4.

Nếu bước 4 in cờ "SẼ BÁN NGAY", Claude báo chủ dự án **trước** khi triển khai.

## 4. Báo cáo cho Claude

Báo cáo gồm các phần sau, theo thứ tự:
1. Kết luận ngắn.
2. Output test đỏ rồi xanh.
3. Phá thử.
4. Chạy khô IJC/AAA.
5. Task B: nguồn nến 0, có trích commit và dòng.
6. Task C: đường dẫn file sao lưu, số dòng, nội dung script SQL, các `SELECT` kiểm.
7. `gitnexus impact` (chạy trước khi sửa) và `detect-changes`.
8. Những điều thấy ngoài phạm vi.

Kết thúc bằng câu: "Tôi không commit, không push, không build hay restart container, không chạy DELETE hay ghi DB thật."
