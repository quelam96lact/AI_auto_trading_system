# Brief 2026-09-01 (đợt 4) — Đo lại lợi thế chiến lược trên dữ liệu đã sạch, và đóng lỗ hổng `sma_cross`

Dành cho agent thực thi. Tự chứa: đọc file này là đủ để làm.

**Đây là việc chặn go-live.** Không phải task viết tính năng. Là một phép đo và
một quyết định.

---

## 1. Đọc kỹ mục này trước — phép đo đã tồn tại, đừng viết lại

`scripts/measure_strategy.py` **đã có** và đã làm đúng thứ brief này cần: chạy
từng mã một với cùng số vốn, cộng dồn, và so với **mua-và-giữ cùng mã / cùng kỳ
/ cùng vốn / cùng phí**. Kết quả đo ngày 15/08 nằm ở
`docs/superpowers/research/2026-08-15-strategy-comparison.md`:

| chiến lược | PnL | chênh so mua-và-giữ | mã thắng BH |
|---|---:|---:|---:|
| `sma_cross` | +11.360.948.249 | −3.468.750.766.392 | 33,9% |
| `daily_breakout` | +33.478.916.106 | −3.446.632.798.534 | 34,2% |
| `octopus_pullback` | −1.792.424.948 | −3.481.904.139.589 | 34,4% |

Ba kết luận đã rút ra hồi đó, **giữ nguyên, đừng đo lại để xác nhận**:

1. Khoảng cách tới mốc của ba chiến lược nằm trong **1% của nhau** — khác biệt
   giữa chúng là nhiễu.
2. `daily_breakout` "lãi" +33,5 tỷ là **artifact dữ liệu**: loại 245 mã chưa
   điều chỉnh chia tách thì thành **−696 triệu** (`a7c6c41`).
3. Bỏ `sma_cross` là đúng, nhưng **không phải vì nó tệ hơn** — mà vì không cái
   nào trong họ này có lợi thế.

**Việc của bạn không phải phát hiện lại ba điều đó.** Là đóng hai lỗ hổng cụ thể
bên dưới.

### Lỗ hổng 1 — `sma_cross` chưa từng được đo trên rổ đã lọc

Chính research doc ghi: *"`sma_cross` **chưa được đo lại trên rổ đã lọc** — nhiều
khả năng khoản +11,4 tỷ của nó cũng cùng nguồn gốc, nhưng đó là suy đoán, không
phải số đo."*

Và `sma_cross` **chính là chiến lược engine đang chạy thật** (`engine/main.py:71`).
Nên câu chưa trả lời lại đúng là câu duy nhất có hậu quả.

### Lỗ hổng 2 — mọi số ở trên đo trên dữ liệu KHÁC dữ liệu hiện tại

Sổ backfill từng bị nhiễm và đã **nạp lại toàn bộ ngày 30/08**. Đo được:

| | 15/08 (theo docstring `measure_strategy.py`) | hôm nay |
|---|---:|---:|
| số dòng `bars_daily` | 2.969.328 | **2.982.903** |
| số mã | — | 1.554 |
| khoảng | — | 2016-01-03 → 2026-08-28 (giờ VN) |

+13.575 dòng, và quan trọng hơn là **nội dung** đã đổi (nạp lại, không phải nạp
thêm). Bảng 15/08 vì thế không còn là mô tả của dữ liệu hiện tại.

---

## 2. Môi trường

- Windows 11, PowerShell + Git Bash. Repo:
  `D:\My_Vault_Obsidian\Project\AI_auto_trading_system`.
- Docker compose đang chạy. Truy vấn:
  `docker exec ai_auto_trading_system-postgres-1 psql -U trading -d trading -c "..."`
- **`DB_DSN` phải dùng `127.0.0.1`, KHÔNG `localhost`** — `localhost` ra IPv6
  trước, treo ~30 giây mỗi lần kết nối.
- Script không tự đọc `.env`: `set -a && . ./.env && set +a` (Git Bash).
- **Lệnh quá 10 phút bị cắt.** Đo 1.554 mã × 3 chiến lược sẽ vượt xa mốc đó.
  **Bắt buộc chạy tách rời** rồi theo dõi file log:
  ```
  Start-Process -NoNewWindow -FilePath "C:\Program Files\Git\bin\bash.exe" `
    -ArgumentList '-lc','cd /d/.../ && set -a && . ./.env && set +a && uv run python scripts/measure_strategy.py --strategy X >> logs/measure_X.log 2>&1'
  ```
  Chạy **smoke test `--limit 20` trước** cho từng chiến lược để biết nhịp, ước
  lượng thời gian, rồi mới chạy đủ. Đừng phóng lệnh 3 tiếng mà chưa biết nó có
  chạy được không.
- Không in giá trị secret ra bất cứ đâu.

---

## 3. Phạm vi phẫu thuật

**Được sửa:** `trading/backtest.py` (chỉ dòng `STRATEGIES`, xem Task 0),
`tests/test_backtest.py` nếu Task 0 làm test đỏ, và tạo mới
`docs/superpowers/research/2026-09-01-strategy-comparison-v2.md`.

**KHÔNG được đụng:** `trading/strategies/*.py` (**tuyệt đối không sửa logic
chiến lược** — sửa rồi đo là đo một thứ khác), `trading/engine/*`,
`trading/real_orders.py`, `trading/risk.py`, `trading/broker.py`,
`trading/paper_broker.py`, `config/config.yaml`, `scripts/measure_strategy.py`,
`scripts/check_price_adjustment.py`, `scripts/sched.sh`,
`scripts/heartbeat_check.py`, và các scheduled task.

> **Đặc biệt cấm:** chỉnh tham số chiến lược (ngưỡng, cửa sổ, hệ số) để ra số
> đẹp hơn. Nếu bạn thấy tham số nào đáng thử khác đi, **báo cáo**, đừng thử.
> Thử rồi báo cáo số tốt nhất trong nhiều lần thử là overfit, và ở đây nó dẫn
> thẳng tới tiền thật.

---

## 4. Task 0 — Đưa `sma_cross` trở lại danh sách ĐO (không phải trở lại engine)

`STRATEGIES` trong `trading/backtest.py:264` hiện chỉ có `daily_breakout` và
`octopus_pullback`; dòng 260 ghi rõ `sma_cross` đã bị gỡ ngày 15/08 theo quyết
định của chủ dự án. Chính việc gỡ đó làm lỗ hổng 1 không thể đóng —
`measure_strategy.py --strategy sma_cross` sẽ báo lỗi choices.

**Thêm `sma_cross` trở lại `STRATEGIES`**, kèm comment nói rõ: đây là **sổ đăng
ký để ĐO**, không phải danh sách chiến lược được phép chạy thật; nó có mặt ở đây
chính vì cần đo lại thứ engine đang chạy. Giữ nguyên dòng comment lịch sử ở 260,
đừng xoá — nó ghi bối cảnh quyết định.

Lớp chiến lược đã có sẵn tại `trading/strategies/sma_cross.py`, **không viết lại**.

→ **Kiểm chứng:** `uv run python scripts/measure_strategy.py --strategy sma_cross --limit 5`
chạy được và in ra bảng. Dán nguyên văn.
→ Nếu việc này làm test nào đỏ (ví dụ test khẳng định registry đúng 2 phần tử),
sửa test cho khớp thực tế mới, **và nói rõ trong báo cáo là đã sửa test nào, vì sao.**

---

## 5. Task A — Dựng lại danh sách loại trừ trên dữ liệu HIỆN TẠI

Danh sách 245 mã của 15/08 dựng trên dữ liệu **trước** đợt nạp lại 30/08. Không
được dùng lại.

```
uv run python scripts/check_price_adjustment.py --emit-exclusions <file> [--dirty-pct 0.05]
```

→ **Kiểm chứng:** số mã bị loại lần này là bao nhiêu, so với **245** của lần
trước. Dán con số cả hai. Chênh lệch lớn (ví dụ còn 20 hoặc lên 600) là **phát
hiện quan trọng về chất lượng đợt nạp lại** — báo cáo rõ, đừng nuốt vào trong
một chữ "đã lọc".

---

## 6. Task B — Đo ba chiến lược, hai rổ

Chạy `measure_strategy.py` cho **cả ba** (`sma_cross`, `daily_breakout`,
`octopus_pullback`), mỗi cái **hai lần**:

- **B1 — rổ đầy đủ** (không `--exclude-file`)
- **B2 — rổ đã lọc** (`--exclude-file <file của Task A>`)

Giữ nguyên mọi tham số mặc định khác (vốn 1 tỷ, toàn kỳ). **Không đổi `--capital`,
không đổi khoảng ngày** — đổi là mất khả năng so với bảng 15/08.

→ **Kiểm chứng:** một bảng 6 dòng, cột: chiến lược | rổ | PnL | mua-và-giữ cùng
kỳ | chênh lệch | số lệnh | số mã sinh lệnh | % mã thắng BH. Dán **nguyên văn**
output của script, không tóm tắt.

→ **Câu phải trả lời thẳng bằng số:** khoản `+11.360.948.249` của `sma_cross` có
biến mất trên rổ đã lọc như `daily_breakout` từng biến mất không?

### Task B' — Đối đầu trực tiếp trên VCB, HPG, TCB

Lặp lại mục 1 của research 15/08 (ba mã, cùng kỳ, vốn 1 tỷ) cho cả ba chiến lược
trên dữ liệu hiện tại, để so trực tiếp với bảng cũ:

```
sma_cross         61 lệnh  win 39,3%  −31.998.591   MaxDD 12,7%
daily_breakout    72 lệnh  win 36,1%  −66.945.194   MaxDD 14,4%
octopus_pullback  25 lệnh  win 56,0%  +50.029.238   MaxDD  2,0%
mua-và-giữ                            +3.995.081.090
```

→ **Kiểm chứng:** bảng mới đặt cạnh bảng cũ. **Số nào lệch nhiều thì nói ra và
nói vì sao** (dữ liệu đổi? mã bị loại khác đi?). Nếu không giải thích được, ghi
"chưa giải thích được" — đừng bịa lý do.

---

## 7. Task C — Viết kết luận, chọn một trong ba, không để lửng

Tạo `docs/superpowers/research/2026-09-01-strategy-comparison-v2.md` theo đúng
cấu trúc file 15/08 (bảng trước, diễn giải sau), và **chọn một** kết cục:

1. **Có chiến lược thắng mua-và-giữ trên rổ đã lọc** ⇒ nêu tên, kèm số. Việc đổi
   `engine/main.py:71` là **task riêng, không làm trong brief này**.
2. **Không có** ⇒ ghi thẳng: *engine chỉ chạy paper để hoàn thiện hạ tầng, không
   bật tiền thật.* **Đây là kết cục hợp lệ, không phải thất bại** — và theo bảng
   15/08 thì đây là kết cục nhiều khả năng nhất. Đừng cố tìm cách diễn đạt cho
   nó nghe tích cực hơn sự thật.
3. **Chưa đủ dữ liệu để kết luận** ⇒ nói rõ thiếu gì và cần gì để đủ.

Phải có một mục riêng trả lời: **`octopus_pullback` MaxDD 2,0% so với 12,7% và
14,4% — trên dữ liệu mới còn giữ được không?** Rủi ro thấp hơn 6 lần với 25 lệnh
là điểm sáng duy nhất trong bảng cũ, nhưng cỡ mẫu 25 lệnh thì **chưa đủ để gọi
là lợi thế**. Nói rõ nó vẫn ở tình trạng đó hay đã khác.

---

## 8. Bẫy đã biết — đọc để khỏi ngã lại

- **"Có lãi" một mình nó vô nghĩa.** Mua-và-giữ 2016–2026 là **+224%**. Mọi
  chiến lược long-only đứng ngoài phần lớn thời gian đều sẽ thua nó. Con số
  duy nhất có ý nghĩa là **chênh lệch so với mốc**.
- **Đừng chạy một danh mục chung 1.554 mã.** Vốn chung sẽ cạn và lặng lẽ chặn
  tín hiệu của các mã phía sau — đúng cái bẫy sizing từng làm hỏng phép đo
  `sma_cross`. `measure_strategy.py` đã chạy từng mã độc lập; **giữ nguyên**.
- **`octopus_pullback` không so trực tiếp được về rổ mã** với hai cái kia: nó có
  bộ lọc thanh khoản ≥ 2 tỷ **bên trong chiến lược** nên chỉ giao dịch ~455 mã.
  Ít lệnh hơn ~14 lần là do bộ lọc, không phải do tín hiệu hiếm hơn. Nói ra điều
  này trong báo cáo, đừng để bảng tự nói dối.
- **Số đo `sma_cross` công bố trước `4a61186` không so sánh được** — lúc đó
  `PaperBroker` chưa cưỡng chế T+2,5 và chưa có mốc mua-và-giữ. Chỉ so với bảng
  15/08 trở đi.

---

## 9. Cấm

- **Không commit, không push.** Claude audit rồi mới commit.
- **Không bật `real_trading_enabled`**, không sửa `config/config.yaml`.
- **Không đổi `engine/main.py`** — kể cả khi tìm ra chiến lược tốt hơn.
- Không gọi API đặt/huỷ lệnh SSI.
- **Không `TRUNCATE`, không `DROP`, không xoá dòng nào.** Phép đo này chỉ ĐỌC
  `bars_daily`. Nếu bạn thấy mình đang viết vào DB, bạn đã đi sai.
- Không in giá trị secret.
- Phát hiện ngoài phạm vi: **báo cáo**, không tự sửa.
- Trước khi sửa symbol nào: `gitnexus_impact`, nói ra blast radius. Sau khi sửa:
  `gitnexus_detect_changes`, đối chiếu với mục 3.

---

## 10. Tiêu chí hoàn thành

- Task 0: `--strategy sma_cross --limit 5` chạy được, output dán nguyên văn.
- Task A: hai con số (245 cũ vs mới), kèm nhận định nếu lệch nhiều.
- Task B: bảng 6 dòng, output nguyên văn, **và câu trả lời thẳng cho câu hỏi
  "+11,4 tỷ của `sma_cross` có biến mất trên rổ đã lọc không"**.
- Task B': bảng ba mã đặt cạnh bảng cũ, giải thích chỗ lệch.
- Task C: file research mới, **chọn đúng một trong ba kết cục**.
- `uv run pytest -m "not integration" -q` xanh (hiện tại: **334 passed**).
- `uv run ruff check trading tests scripts` sạch.
- Việc nào không làm được thì nói rõ vì sao. **Không đoán, không tóm tắt bằng
  chứng thành chữ "pass".** Một phép đo bị bịa là tệ hơn không đo.
