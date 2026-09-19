# Brief đợt 62 — Sửa đòn vay ảo, đo lại buy-and-hold có nhịp

Ngày giao: 19/09/2026 (thứ Bảy, khuya).
Base: main hiện tại (đợt 61 **chưa commit**, các file của nó vẫn nằm chưa theo dõi trong cây làm
việc — xem mục 0).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Đọc trước: đợt 61 bị từ chối, vì sao

`docs/superpowers/research/2026-09-19-dot-61-audit-tu-choi-don-vay-ao.md` — đọc toàn bộ trước
khi sửa. Tóm tắt: `simulate_symbol_regime_hold` tính `qty` **một lần duy nhất ở đầu kỳ 10 năm**
rồi dùng lại cho mọi lần mua lại sau đó, không kiểm `cash` có đủ không. Khi giá lúc mua lại cao
hơn đáng kể so với lúc bán, `cash` bị **âm** — đòn bẩy ảo, không tồn tại trong tài khoản thật.
Bằng chứng đo được: cash âm **−200,7% vốn gốc** trong một kịch bản dựng tay.

Ba file của đợt 61 hiện **chưa commit, chưa xoá**: `scripts/measure_regime_hold.py`,
`tests/test_regime_hold.py`, `docs/superpowers/research/2026-09-19-dot-61-*.md`. Brief này sửa
hai file đầu **tại chỗ**, không viết lại từ đầu — phần đọc dữ liệu, phần mua-và-giữ thuần
(`bh_pnl`, `bh_daily_equity`), phần đếm chuyển trạng thái (`count_regime_switches`), và toàn bộ
`run_regime_hold_benchmark`/`main()` **đều đúng, giữ nguyên**. Lỗi khu trú trong đúng một hàm.

---

## 1. Ràng buộc — giống hệt đợt 61

Không đụng `trading/`. Không sửa `config/config.yaml`. Không commit, không push.
`real_trading_enabled` giữ `false`. Không ghi DB. Không in secret.

---

## Task 1 — Sửa `simulate_symbol_regime_hold`: `qty` tính lại mỗi lần mua, `cash` không bao giờ âm

### 1.1. Quy tắc đúng, đóng băng, không tự diễn giải thêm

Mỗi lần trạng thái đổi từ TIỀN MẶT → NẮM GIỮ:

1. Tính `qty` mới **từ `cash` đang có tại đúng thời điểm đó** (không phải từ vốn gốc, không phải
   từ `qty` của lần mua trước):
   ```
   buy_p = Open(d) * (1 + slip)
   qty = int(cash // (buy_p * (1 + fee_rate)))
   qty = (qty // lot_size) * lot_size
   ```
2. Nếu `qty < lot_size` hoặc `qty <= 0` (tiền còn lại không đủ mua nổi 1 lô): **không mua**, ở
   lại trạng thái TIỀN MẶT, ghi nhận rõ trong kết quả trả về (thêm trường
   `skipped_buys: int` — đếm số lần định mua nhưng không đủ tiền). Đây không phải lỗi, là hành vi
   đúng của một tài khoản thật hết tiền.
3. Sau khi mua: `cash -= qty * buy_p * (1 + fee_rate)`. **Bất biến bắt buộc: `cash >= 0` sau mọi
   giao dịch, mọi lúc, không có ngoại lệ.**

Mỗi lần trạng thái đổi từ NẮM GIỮ → TIỀN MẶT: giữ nguyên như đợt 61 (bán toàn bộ `pos` đang có,
không đổi).

### 1.2. Vì sao không "chia đều lại theo tỷ trọng ban đầu"

Đừng nhầm việc này với việc tái cân bằng danh mục (rebalance) giữa các mã — đó là câu hỏi khác,
không phải phạm vi brief này. Ở đây mỗi mã đã có `cash` riêng của chính nó xuyên suốt kỳ đo
(đúng cấu trúc `simulate_symbol_regime_hold` chạy độc lập từng mã đã có), nên "cash đang có" ở
mục 1.1 là cash **của riêng mã đó**, không lấy từ mã khác. Không đổi kiến trúc chia vốn theo mã.

### 1.3. Kiểm chứng

1. **Test mới, bắt buộc**: `test_cash_khong_bao_gio_am` — dựng đúng kịch bản đã lộ lỗi (bán ở
   giá thấp, mua lại ở giá cao gấp 2–3 lần), khẳng định `cash` không âm ở **bất kỳ thời điểm nào**
   trong suốt mô phỏng (không chỉ ở cuối kỳ). Thêm trường trả về `min_cash_seen: float` hoặc
   tương đương để test kiểm được giá trị nhỏ nhất `cash` từng đạt.
2. **Sửa `test_mua_ban_dung_gia_va_phi`** (đợt 61 viết sai vì dựa trên công thức lỗi — được phép
   sửa test này, vì chính hợp đồng đang đổi, giống tiền lệ đợt 56 §1.3b). Tính tay lại đúng: nhịp
   thứ hai phải dùng `qty` **mới** tính từ `cash` sau nhịp một, không phải `qty` ban đầu.
3. **Chứng minh test phân biệt được**: tạm khôi phục lỗi cũ (dùng lại `qty` cố định), chạy
   `test_cash_khong_bao_gio_am` → phải đỏ đúng bằng bằng chứng ở mục audit (`cash` âm). Khôi
   phục, dán `git diff` khớp đúng phần sửa.
4. Ba test còn lại của đợt 61 (`test_khong_doi_khi_regime_khong_doi`,
   `test_khong_nhin_trom_tuong_lai`, `test_max_drawdown_dung`) **không đổi hành vi mong đợi** —
   chạy lại, phải vẫn xanh. Nếu một trong ba đỏ sau khi sửa, dừng lại và báo cáo, đừng sửa test
   đó để nó xanh trở lại — nghĩa là còn sai chỗ khác.

---

## Task 2 — Đo lại toàn bộ, đối chiếu với số đã bị từ chối

Chạy lại đúng hai kỳ như đợt 61 (2016-01-04 → 2022-12-31 và 2023-01-01 → 2026-08-28), đúng
lệnh:

```bash
uv run python scripts/measure_regime_hold.py --task all --exclude-file exclusions.txt
```

Với mỗi kỳ, báo cáo:

1. PnL "buy-and-hold có nhịp" (bản sửa) — **và** con số cũ của đợt 61, đặt cạnh nhau để thấy
   chênh lệch bao nhiêu.
2. **Tổng số lần `skipped_buys`** (không đủ tiền mua lại) trên toàn rổ — đây là con số mới,
   không có ở đợt 61, và nó tự nó là một phát hiện: nếu số này lớn, nghĩa là nhiều mã "hết đạn"
   giữa chừng sau một hồi thua lỗ, và không bao giờ tham gia đủ vào các đợt tăng sau đó.
3. Max drawdown — tính lại, **phải khác** số đợt 61 vì đường vốn giờ đúng.
4. So với mua-và-giữ thuần cùng kỳ (số này không đổi so với đợt 61, tự tính lại để xác nhận
   không lệch).

**Không cần đóng băng quy tắc mới** — quy tắc HOLD/CASH theo `regime(d-1)` giữ nguyên như đợt 61
mục 2.1, chỉ có cơ chế mua lại (mục 1.1 ở trên) là thay đổi.

---

## 2. Báo cáo cho Claude

1. `git diff scripts/measure_regime_hold.py` — chỉ phần trong `simulate_symbol_regime_hold`
   đổi, phần còn lại của file **không đổi một dòng**.
2. `git diff tests/test_regime_hold.py`.
3. Bằng chứng test phân biệt được (mục 1.3.3), dán nguyên văn output đỏ.
4. Bảng đối chiếu Task 2: số cũ (bị từ chối) cạnh số mới, cả hai kỳ.
5. `uv run pytest -m "not integration" -q` — không có test nào đỏ thêm ngoài
   `test_backtest_cli.py::test_cli_registry_no_longer_offers_sma_cross` (đã biết từ đợt 9).
6. `uv run ruff check trading tests scripts` sạch.

**Không commit, không push.**

---

## 3. Điều KHÔNG làm

- **Không đổi quy tắc HOLD/CASH** (regime, ngưỡng 0,40/0,60) — chỉ sửa cơ chế mua lại.
- **Không rebalance giữa các mã.**
- **Không thêm mô hình vay ký quỹ (margin) thật** — nếu không đủ tiền thì đứng ngoài
  (`skipped_buys`), không mô phỏng vay có lãi suất. Đó là lựa chọn bảo thủ đúng, không phải thiếu
  sót.
- **Không đụng `trading/`, không sửa engine.**
