# Đợt 106 — Đo module D (VWAP + Volume Profile + Order Flow) trên BTCUSDT perp 1H

Ngày: 2026-09-26. Brief: `docs/superpowers/plans/2026-09-26-brief-dot-106-do-module-d-vwap-volume-profile.md`.
Code: `trading/perp_value_pullback.py`, `tests/test_perp_value_pullback.py`,
`scripts/measure_perp_value_pullback.py`, `tests/test_measure_perp_value_pullback.py`
(+ mở rộng `Literal` của `PerpTrade.exit_reason` trong `trading/perp_backtest.py`).
Dữ liệu: BTCUSDT perp, nến 1H hai cửa sổ CHÍNH/LẶP LẠI, profile dựng từ nến 5m.

## 1. Kết luận hai dòng

**D KHÔNG CÓ LỢI THẾ.** CHÍNH đạt tiêu chí (1) với 42 lần vào nhưng hỏng tiêu chí (2) vì
`net_after_funding = −19,20` USDT; LẶP LẠI cũng âm (`−32,96`), nên theo §2.6 tiêu chí (3) in
`BỎ QUA` và không chạy đối chứng ngẫu nhiên.

Bộ lọc flow **giảm lỗ nhưng không lật dấu** ở cả hai cửa sổ: CHÍNH −42,69 → −19,20;
LẶP LẠI −59,06 → −32,96 (đơn vị USDT, sau funding). Không có biến thể nào dương.

## 2. Chỗ tài liệu §7 khác §2 của brief

Đã đọc tài liệu §7.1–§7.4 (dòng 202–238) và đối chiếu từng dòng với §2 brief. Không tự đổi gì.

| # | Tài liệu §7 | Brief §2 | Xử lý |
|---|---|---|---|
| 1 | §7.2 bảng: xác nhận gồm **3** điều kiện (`đóng trên mức được chạm`, `nến xanh`, `close > high nến trước`) | §2.2 thêm điều kiện thứ **4**: `close_t > VAH` (acceptance ngoài vùng giá trị) | Brief siết hơn; tài liệu chỉ nói điều này ở văn xuôi ("Không trade nếu close nằm trong vùng VAL–VAH"). Làm theo brief. |
| 2 | §7.2: "Trong tối đa 3 nến sau regime, low chạm VWAP hoặc VAH" (đọc được thành: chạm ở nến sau) | §2.2: regime đúng tại ≥1 nến trong `{t−3,t−2,t−1}`, **chạm và xác nhận cùng nến `t`** | Cùng nghĩa; brief chốt cách hiểu "cùng một nến" (dòng 91). Làm theo brief. |
| 3 | §7.2: "Không trade nếu close nằm trong vùng VAL–VAH" (văn xuôi) | §2.2: `close_t > VAH` (LONG) / `close_t < VAL` (SHORT) | Đã gộp vào #1. |
| 4 | §7.3: bỏ trade nếu stop–entry **nhỏ hơn 0,20·ATR14** hoặc lớn hơn 1,50·ATR14 | §2.3 giống, nhưng `R = |entry − stop|` với `entry` là **giá khớp thật** sau gap | Brief ghim công thức. Làm theo brief. |
| 5 | §7.3: "spread, slippage hoặc delay làm chi phí vào/ra vượt 0,15R" | §2.3 ghim `entry·2·SLIPPAGE_BPS/1e4 > 0,15·R` và **không** tính phí sàn vào đây | Brief ghim công thức. Làm theo brief. |
| 6 | §7.3: tránh entry quá gần "Profile High, Profile Low **hoặc HVN**" | §2.3: chỉ PH/PL; **HVN/LVN tắt** | Tài liệu tự cho phép tắt ("để filter này tắt trong baseline"). Làm theo brief. |
| 7 | §7.3: "Nếu sau 12 nến chưa đạt 1R, đóng toàn bộ" | §2.3 (e): `TIME` sau 12 nến **khi chưa chốt TP1** | Cùng nghĩa. |
| 8 | §7.3: "dời stop phần còn lại về entry cộng/trừ chi phí **chỉ sau khi TP1 khớp**" | Luật (b): BE áp dụng **từ nến sau** nến TP1 | Brief ghim mốc thời gian; tài liệu không nói rõ "nến sau". Làm theo brief. |
| 9 | §7.2: magnitude flow "abs(delta) >= median abs(delta) của 20 nến trước" | §2.2/§2.1: cùng công thức, ghim thêm "tử số là nến `t`, cửa sổ 20 nến **không gồm `t`**" | Làm theo brief. Đây là chỗ đã bị phá thử (ii). |
| 10 | §7.3: "1H đầu UTC có dữ liệu trade chưa đầy đủ" (văn xuôi, trong danh sách "không vào") | §2.2 dòng 57: **luật chặn cứng** — `t` là nến 00:00 UTC thì không xét tín hiệu | Brief biến văn xuôi thành luật cứng. Làm theo brief. |
| 11 | §7.1: "Volume Profile: ngày UTC trước, 48 rows, VA 70%" | §2.1 khớp (48 hàng, 0,70, từ **toàn bộ** nến 5m của D−1, đủ 288 nến) | Khớp. |
| 12 | §7.4: cảnh báo D dễ hỏng khi anchor UTC không đại diện nhịp thanh khoản | Không có mục tương ứng trong §2 | Ghi nhận, không đo trong đợt này. |

Không có chỗ nào tài liệu nói **ngược** brief; các khác biệt đều là brief siết/ghim công thức.

## 3. Số liệu nạp 5m và đối chiếu volume

Nạp: `uv run python scripts/binance_vision.py --mode klines --symbol BTCUSDT --interval 5m
--from 2020-01-01 --to 2026-08-31` — nền `proc_8d687439d81f`, pid 28640,
`BAT DAU 19:51:07` → `KET THUC 19:59:27`, `EXIT=0`. Log: `…\Temp\run_dot106_load5m.log`.

Kiểm chứng bằng SQL (`date_trunc('hour', ts)`):

```
== So nen 5m theo nam (ky vong 105408/105120x3/105408/105120/69984) ==
  2020: 105408   2021: 105120   2022: 105120   2023: 105120
  2024: 105408   2025: 105120   2026: 69984    TONG: 701280
== So nen 1h theo nam ==
  2020: 8784  2021: 8760  2022: 8760  2023: 8760  2024: 8784  2025: 8760  2026: 5832
== So NGAY co < 288 nen 5m ==
  0
== Doi chieu Sigma volume 5m vs 1h theo gio ==
  gio_chung=58440  gio_lech>0,1%=6  gio_thieu_nen=0
== 5 gio lech nhieu nhat ==
  2023-11-10 16:00:00+00:00  5m=2146.0720  1h=25855.7730  lech=91.699834%
  2023-11-10 15:00:00+00:00  5m=1351.5700  1h=13404.8650  lech=89.917317%
  2025-01-29 01:00:00+00:00  5m=2996.6660  1h=3718.5730   lech=19.413549%
  2025-01-29 02:00:00+00:00  5m=3606.9550  1h=3752.3200   lech=3.874003%
  2022-07-04 11:00:00+00:00  59967.5420  1h=60081.9890    lech=0.190485%
```

- Tổng 5m **701.280** khớp brief; từng năm khớp đúng danh sách brief; số nến 1h (58.440) cũng khớp §1.
- **0 ngày** có < 288 nến 5m ⇒ mọi ngày đều dựng được profile; script đo in `ngay_du_288=2435`.
- **6 giờ** lệch > 0,1% trên 58.440 giờ chung. Hai giờ nặng nhất (2023-11-10 15:00 và 16:00)
  lệch **89,9%** và **91,7%**: volume 5m nhỏ hơn hẳn volume 1h cùng giờ. Ghi nguyên văn,
  **không tự lấp, không đoán nguyên nhân**. Đã kiểm 0 giờ thiếu nến và 0 ngày thiếu nến, nên
  lệch không đến từ nến thiếu. Ảnh hưởng lên phép đo: profile của ngày 2023-11-11 dựng từ
  ngày 2023-11-10 (có 2 giờ lệch) — đúng 1 ngày trong 2.435 ngày.

## 4. Output test

```
$ uv run pytest tests/test_perp_value_pullback.py tests/test_measure_perp_value_pullback.py -q
...............................................                          [100%]
47 passed in 0.77s

$ uv run pytest -m "not integration" -q
........................................................................ [ 96%]
.......................................                                  [100%]
1119 passed, 127 deselected in 21.04s

$ uv run ruff check trading tests scripts/measure_perp_value_pullback.py
All checks passed!
```

- 47 test mới = 40 engine + hàm thuần (`tests/test_perp_value_pullback.py`) và 7 `mag_ok`
  (`tests/test_measure_perp_value_pullback.py`). Mốc brief 1072 + 47 = **1119**, khớp.
- Phủ test: 11 test hàm thuần (VWAP 3 nến / reset UTC / thiếu nến · POC hoà · VA mở rộng hoà ·
  hết hàng một phía · HLC3 = hi · biên 287 nến), 3 test ghép ngày D−1→D, 6 test `mag_ok`,
  2 test regime 5 điều kiện, và 24 test engine: tín hiệu LONG đúng `t`, sửa nến `t+1` không đổi
  tín hiệu, không tín hiệu ở 00:00 UTC (có đối chứng 01:00 phát), thiếu profile/VWAP/chạm/xác
  nhận/`close > VAH`, hết hạn 2 nến, ba bộ lọc (R/chi phí/vùng cản) + ablation,
  `entry_filter` luôn `False`, spy chứng minh `entry_filter` không được gọi khi `random_entry`,
  luật thoát (a)–(g), và SHORT đối xứng cho (a) và (c).

## 5. Phá thử

Sao lưu **ra ngoài repo** (`%LOCALAPPDATA%\Temp\backup_dot106_*.py`), khôi phục bằng `cp`,
xác nhận `sha256sum`. Không dùng `git checkout/restore/stash`.

| Phép phá | Cách phá | Test đỏ | Khôi phục |
|---|---|---|---|
| (i) profile dùng nến ngày D thay D−1 | `out[src_day + timedelta(days=1)] = prof` → `out[src_day] = prof` | `test_profile_for_days_uses_previous_day_data`, `test_profile_for_days_skips_day_with_287_bars` (2 đỏ) | `457b66a232aa4ad6…` khớp, xanh lại |
| (ii) cửa sổ `mag_ok` gồm nến `t` | dời `abs_deltas.append(...)` lên **trước** khi lấy cửa sổ | `test_mag_ok_manual_window_of_20` (1 đỏ) | `f34913963bf77862…` khớp, xanh lại |
| (iii) đảo thứ tự: xét TP1 trước SL | chèn khối xét TP1 lên trước khối stop và thêm `not bar_done` vào điều kiện stop (LONG) | `test_engine_exit_f_stop_and_tp1_same_bar_takes_stop` (1 đỏ) | `457b66a232aa4ad6…` khớp, xanh lại |
| (iv) stop BE áp ngay trong nến chốt TP1 | sau khi TP1 khớp trong nến, đóng tiếp chân còn lại bằng BE nếu `low ≤ be_stop` (LONG) | `test_engine_exit_b_tp1_then_be_next_bar`, `test_engine_exit_c_tp1_then_tp2` (2 đỏ) | `457b66a232aa4ad6…` khớp, xanh lại |

Kiểm tra cuối: hash cả 5 file (engine, script đo, 2 file test, `perp_backtest.py`) **KHỚP**
backup. Cả 4 phép phá đều **thật sự vi phạm luật** (đã kiểm lại trước khi kết luận):

- (ii) làm theo đúng bài học đợt 105: nếu chỉ dịch cửa sổ mà `append` vẫn ở sau thì nến `t`
  không lọt vào cửa sổ và phép phá **không vi phạm gì** — lần này dời `append` lên trước.
- (iv) **chỉ đổi `pos_be_from_idx = i+1` thành `= i` là vô hiệu**: khối (3) bị `bar_done` chặn
  nên trong nến TP1 không có gì chạy tiếp; phải chèn khối đóng chân 2 bằng BE mới đúng nghĩa
  "BE áp ngay trong nến TP1". Đã kiểm bằng cách đọc lại luồng mã trước khi kết luận.

**Một test của tôi không phân biệt được hai cách hiểu.** Với phép phá (ii), test
`test_mag_ok_window_excludes_bar_t` **vẫn xanh** (bộ số `[1]*10 + [100]*10 + [45]` cho ra
`False` ở cả hai cách hiểu, vì cửa sổ 20 phần tử khi đã gồm `t` lại **rơi mất giá trị `1` đầu
tiên**, trung vị thành 72,5). Test bắt được phép phá là `test_mag_ok_manual_window_of_20`;
test kia giữ nguyên nhưng tôi ghi rõ nó **không** có tác dụng phân biệt như tôi định.

## 6. Output đo nguyên văn

Lệnh đúng như brief: `uv run python scripts/measure_perp_value_pullback.py`
(`BAT DAU 20:21:35` → `KET THUC 20:21:58`, `EXIT=0`). Log: `…\Temp\run_dot106.log`.
`sha256sum` của engine và script đo **trước và sau** khi chạy **giống nhau**
(`f88af90d05b8e410…`, `764f28bd029207df…`) — code không đổi trong lúc đo.

```
### Nap nen 5m 2020-01-01 -> 2026-08-31
  nen_5m=701280  ngay=2435  ngay_du_288=2435  tg=8.2s
  profile dung duoc cho 2435 ngay (dong hoa 9.1s)

### CHINH: 2020-01-01 00:00:00+00:00 -> 2024-01-01 00:00:00+00:00
  nen_1h=35064  funding=4383  nen_thieu_flow=0  flow_khong_hop_le=0  mag_ok_true=17372
  [baseline]  (1.5s)
  baseline       vao=  42 chan=  84 tin_hieu= 281 het_han= 94 bo[flow=673 R=116 phi=  0 can= 29]
    net=    -18.27 funding=    0.93 net_sau_funding=    -19.20 win=47.6% PF=0.68 maxDD=6.11%
    chieu: LONG=56/12.24 SHORT=28/-30.51
    ly_do_thoat: BE=11/0.26 SL=44/-57.72 TIME=2/0.39 TP1=19/19.18 TP2=8/19.61
    theo_nam: 2020=24/-0.55 2021=18/7.57 2022=26/-17.03 2023=16/-8.26
  [flow_tat]  (2.7s)
  flow_tat       vao= 174 chan= 348 tin_hieu= 875 het_han=290 bo[flow=  0 R=285 phi=  8 can=118]
    net=    -40.78 funding=    1.91 net_sau_funding=    -42.69 win=50.0% PF=0.82 maxDD=12.94%
    chieu: LONG=190/-5.66 SHORT=158/-35.11
    ly_do_thoat: BE=45/-1.73 EMA20=1/0.32 SL=162/-215.47 TIME=12/-5.83 TP1=87/89.20 TP2=41/92.75
    theo_nam: 2020=84/1.93 2021=102/-0.68 2022=86/-24.10 2023=76/-17.92
  [chi_phi_tat]  (1.1s)
  chi_phi_tat    vao=  42 chan=  84 tin_hieu= 281 het_han= 94 bo[flow=673 R=116 phi=  0 can= 29]
    net=    -18.27 funding=    0.93 net_sau_funding=    -19.20 win=47.6% PF=0.68 maxDD=6.11%
    chieu: LONG=56/12.24 SHORT=28/-30.51
    ly_do_thoat: BE=11/0.26 SL=44/-57.72 TIME=2/0.39 TP1=19/19.18 TP2=8/19.61
    theo_nam: 2020=24/-0.55 2021=18/7.57 2022=26/-17.03 2023=16/-8.26
  [vung_can_tat]  (1.4s)
  vung_can_tat   vao=  70 chan= 140 tin_hieu= 274 het_han= 94 bo[flow=665 R=110 phi=  0 can=  0]
    net=    -31.15 funding=    1.17 net_sau_funding=    -32.32 win=45.7% PF=0.69 maxDD=10.65%
    chieu: LONG=80/29.93 SHORT=60/-61.08
    ly_do_thoat: BE=18/-0.45 SL=76/-99.00 TIME=2/0.38 TP1=31/35.21 TP2=13/32.71
    theo_nam: 2020=42/13.11 2021=24/3.45 2022=46/-24.66 2023=28/-23.04
  mua-giu BTC: +490.03%
  (cua so CHINH xong sau 7.6s)

### LAP LAI: 2024-01-01 00:00:00+00:00 -> 2026-09-01 00:00:00+00:00
  nen_1h=23376  funding=2922  nen_thieu_flow=0  flow_khong_hop_le=1  mag_ok_true=11565
  [baseline]  (0.8s)
  baseline       vao=  47 chan=  94 tin_hieu= 254 het_han= 63 bo[flow=355 R=126 phi=  1 can= 17]
    net=    -32.79 funding=    0.17 net_sau_funding=    -32.96 win=42.6% PF=0.51 maxDD=8.73%
    chieu: LONG=54/-11.56 SHORT=40/-21.22
    ly_do_thoat: BE=13/0.32 EMA20=1/0.21 SL=52/-65.69 TIME=4/-0.66 TP1=19/22.78 TP2=5/10.25
    theo_nam: 2024=24/0.92 2025=32/-8.69 2026=38/-25.02
  [flow_tat]  (1.7s)
  flow_tat       vao= 138 chan= 276 tin_hieu= 567 het_han=166 bo[flow=  0 R=207 phi=  3 can= 53]
    net=    -58.25 funding=    0.82 net_sau_funding=    -59.06 win=49.3% PF=0.66 maxDD=13.78%
    chieu: LONG=164/-26.33 SHORT=112/-31.91
    ly_do_thoat: BE=41/-0.58 EMA20=2/0.69 SL=136/-170.61 TIME=10/0.16 TP1=65/66.71 TP2=22/45.39
    theo_nam: 2024=86/-5.41 2025=112/-23.82 2026=78/-29.01
  [chi_phi_tat]  (0.9s)
  chi_phi_tat    vao=  48 chan=  96 tin_hieu= 254 het_han= 63 bo[flow=355 R=126 phi=  0 can= 17]
    net=    -35.25 funding=    0.17 net_sau_funding=    -35.42 win=41.7% PF=0.49 maxDD=9.22%
    chieu: LONG=54/-11.46 SHORT=42/-23.80
    ly_do_thoat: BE=13/0.32 EMA20=1/0.21 SL=54/-68.05 TIME=4/-0.65 TP1=19/22.70 TP2=5/10.22
    theo_nam: 2024=26/-1.73 2025=32/-8.64 2026=38/-24.89
  [vung_can_tat]  (0.9s)
  vung_can_tat   vao=  60 chan= 120 tin_hieu= 244 het_han= 61 bo[flow=349 R=122 phi=  1 can=  0]
    net=    -28.77 funding=    0.27 net_sau_funding=    -29.04 win=45.0% PF=0.64 maxDD=7.03%
    chieu: LONG=70/-16.19 SHORT=50/-12.57
    ly_do_thoat: BE=16/0.41 EMA20=1/0.21 SL=62/-78.24 TIME=4/-2.12 TP1=27/30.57 TP2=10/20.40
    theo_nam: 2024=40/-6.40 2025=40/-0.85 2026=40/-21.51
  mua-giu BTC: +84.81%
  (cua so LAP LAI xong sau 4.9s)

### DOI CHUNG NGau NHIEN: BO QUA
  ly do: CHINH vao=42 net_sau_funding=-19.20

### KET LUAN (§2.6)
  (1) CHINH >= 30 lan vao: 42 -> DAT
  (2) CHINH net_sau_funding > 0: -19.20 -> HONG
  (3) doi chung ngau nhien: BO QUA (CHINH hong (1) hoac (2))
  (4) LAP LAI net_sau_funding > 0: -32.96 -> HONG
  => D KHONG CO LOI THE.

Tong thoi gian chay: 21.6s
```

### 6b. Đọc số

**Ablation (CHÍNH / LẶP LẠI, `net_after_funding` USDT, số lần vào):**

| Biến thể | CHÍNH | LẶP LẠI |
|---|---|---|
| baseline (flow BẬT, đủ 2 bộ lọc) | −19,20 / 42 | −32,96 / 47 |
| flow TẮT | −42,69 / 174 | −59,06 / 138 |
| bộ lọc chi phí TẮT | −19,20 / 42 (**giống hệt baseline**) | −35,42 / 48 |
| bộ lọc vùng cản TẮT | −32,32 / 70 | −29,04 / 60 |
| mua-giữ BTC | +490,03% | +84,81% |

- Bộ lọc chi phí TẮT **không đổi gì** ở CHÍNH: `bo[phi=0]` ⇒ trong cửa sổ này không có lệnh nào
  bị bộ lọc chi phí chặn, nên ablation đó **không mang thông tin**. Ở LẶP LẠI nó chặn **1** lệnh
  (48 → 47 lần vào, `−35,42` → `−32,96`).
- Cả 4 biến thể ở cả 2 cửa sổ đều âm. Biến thể **kém nhất** ở cả hai là flow TẮT.
- Bộ lọc flow chặn 673 tín hiệu ở CHÍNH và 355 ở LẶP LẠI; nó cắt 132/91 lần vào và làm **giảm**
  số lỗ tuyệt đối, nhưng **PF lại thấp hơn** (0,68 so với 0,82 ở CHÍNH; 0,51 so với 0,66 ở LẶP LẠI).
- Phân rã Long/Short (chân, USDT): CHÍNH LONG 56/+12,24 · SHORT 28/−30,51; LẶP LẠI LONG 54/−11,56 ·
  SHORT 40/−21,22. SHORT lỗ nặng hơn LONG ở cả hai cửa sổ.
- Theo `exit_reason` (chân, USDT): CHÍNH SL 44/−57,72 là nguồn lỗ chính, TP1 19/+19,18 và TP2 8/+19,61
  bù lại một phần, BE 11/+0,26, TIME 2/+0,39. LẶP LẠI: SL 52/−65,69, TP1 19/+22,78, TP2 5/+10,25,
  BE 13/+0,32, EMA20 1/+0,21, TIME 4/−0,66.
- Theo năm (chân, USDT): CHÍNH 2020 24/−0,55 · 2021 18/+7,57 · 2022 26/−17,03 · 2023 16/−8,26;
  LẶP LẠI 2024 24/+0,92 · 2025 32/−8,69 · 2026 38/−25,02. Năm 2026 (đến 31/08) là năm lỗ nặng nhất.
- Funding **gần 0** ở mọi biến thể (0,17–1,91 USDT) ⇒ không phải nguyên nhân gây lỗ.

## 7. `gitnexus_impact` (chạy TRƯỚC khi sửa) và `detect_changes`

`impact PerpTrade` upstream, **chạy trước** khi mở rộng `exit_reason`:
**1 mục, `risk_level = low`** (chỉ `scripts/measure_perp_modules.py` import `PerpTrade`),
**không có HIGH/CRITICAL** ⇒ được phép mở rộng `Literal` thêm `TP1/TP2/BE/EMA20`.

`detect_changes` (sau khi xong):

```json
{"summary": {"changed_count": 3, "affected_count": 0, "changed_files": 1, "risk_level": "low"},
 "changed_symbols": ["Variable:trading/perp_backtest.py:clipped",
                     "Property:trading/perp_backtest.py:PerpTrade.clipped",
                     "Class:trading/perp_backtest.py:PerpTrade"],
 "affected_processes": []}
```

**Cảnh báo về chính công cụ:** `changed_files = 1` và chỉ thấy `perp_backtest.py`, **không** thấy
`trading/perp_value_pullback.py`, `scripts/measure_perp_value_pullback.py` hay 2 file test —
vì index GitNexus không theo dõi file untracked. **Không đọc kết quả này thành "chỉ có 1 file thay đổi"**;
đợt 105 đã gặp đúng lỗ hổng này.

## 8. Những điều thấy ngoài phạm vi

1. **Nhánh `R < 0,20·ATR` của bộ lọc R là bất khả thi về mặt toán.** Với §2.2, điều kiện chạm
   `|low_t − L| ≤ 0,25·ATR_t` ⇒ `low_t ≥ L − 0,25·ATR_t` ⇒ `stop = min(low_t, L − 0,25·ATR_t)`
   **luôn** bằng `L − 0,25·ATR_t`. Do đó `R = (high_t − L) + 0,30·ATR_t`, mà xác nhận đòi
   `close_t > L` nên `high_t > L` ⇒ `R > 0,30·ATR_t > 0,20·ATR_t`. **Chỉ nhánh `R > 1,50·ATR` mới
   có thể chặn.** Đây là chứng minh trên mã, **không phải số đo**; đợt này không đo riêng nhánh đó.
2. **Phép đo chính thức chỉ chạy một lần, nhưng trước đó tôi có chạy thử `--skip-null`** (22,8s)
   để bắt lỗi runtime. Bản chạy thử cho **cùng** số với bản chính thức (42 lần vào, `−19,20`).
   Sai khác duy nhất về mã giữa hai lần: bootstrap `sys.path`, `ruff --fix` (8 lỗi) và việc buộc
   tham số cho `_close_leg`. Sau khi sửa, đã chạy lại **toàn bộ 47 test** trước khi đo chính thức.
3. **`ruff` ban đầu báo 34 lỗi trong file của tôi** (repo trước đó sạch): 27 × `B023` (closure
   trong vòng lặp), 1 × `SIM114`, phần còn lại ở test. Đã sửa: buộc 11 biến trạng thái vị thế qua
   tham số mặc định của `_close_leg`; riêng `pos_would_liquidate` phải đọc giá trị sống (cờ có thể
   được bật **sau** khi hàm được định nghĩa trong cùng nến) nên giữ **1 dòng `# noqa: B023`** có
   ghi chú lý do. Đây là chỗ tôi muốn Claude soi lại thay vì tự cho là ổn.
4. **6 giờ lệch volume 5m/1h** đã nêu ở §3; nặng nhất 2023-11-10 15:00–16:00 (89,9% và 91,7%).
5. **Test của tôi không phân biệt được hai cách hiểu** (đã nêu ở §5): `test_mag_ok_window_excludes_bar_t`
   xanh dưới cả hai cách hiểu ⇒ nó giữ vai trò ghi lại cách hiểu, không phải test phản chứng.
6. **Cửa sổ LẶP LẠI có 1 nến flow không hợp lệ** (`flow_khong_hop_le=1`, cùng hiện tượng
   `quote_volume=0` đã gặp đợt 105) — `mag_ok` trả `None` cho nến đó và cho mọi cửa sổ chứa nó,
   không nội suy.
7. **Lỗi của tôi trong quá trình làm** (không phải lỗi còn lại, nhưng phải kể):
   - engine so `close_t > close_{t-1}` thay vì `close_t > high_{t-1}` — **test bắt được**, đã vá
     (thêm `high`/`low` vào `_Snap`);
   - `pos_be_from_idx = -1` làm `i >= -1` luôn đúng ⇒ stop BE áp ngay từ nến vào lệnh, phá luật (a)
     — **phát hiện khi thiết kế test**, đã vá;
   - kịch bản test ban đầu để nến "value" cũng thoả xác nhận nên tín hiệu bật ở nến 11:00 thay vì
     12:00, và bản SHORT sinh nến `low > high` — cả hai là lỗi kịch bản của tôi, đã sửa (cho nến
     value thành doji để chỉ nến tín hiệu mới xanh);
   - phép phá (iv) nếu chỉ đổi chỉ số `pos_be_from_idx` thì **không vi phạm gì** (đã kiểm lại luồng
     mã trước khi chọn cách phá đúng nghĩa).
8. **`detect_changes` không thấy 4 file mới** (mục 7) — lỗ hổng của index, không phải bằng chứng
   rằng các file đó không đổi.
9. `Bar.volume` có annotation `int` nhưng loader truyền `float` (đã gặp đợt 105, chưa sửa vì ngoài
   phạm vi brief này).

Tôi không commit, không push, không đụng BingX API, không đọc dữ liệu từ 2026-09-01.

---

## Ghi chú kiểm chứng của Claude (26/09/2026)

**Kết luận không đổi: D KHÔNG CÓ LỢI THẾ.** Claude đọc toàn bộ engine và thấy hai chỗ lệch khỏi §2.2 của brief. Cả hai đã được sửa rồi đo lại.

### 1. `ema20_prev3` lệch một nến

`ema20_history` đã gồm EMA20 của chính nến `x` ở phần tử cuối, nên `[-3]` là EMA20_{x-2}. Brief yêu cầu EMA20_{x-3}, tức `[-4]`.
- **Sửa:** tách hàm `_ema20_lag3` và thêm `test_ema20_lag3_is_three_bars_before_current`.
- **Phá thử:** đưa `[-3]` trở lại thì test mới đỏ; khôi phục thì xanh lại.

Các test regime cũ không bắt được lỗi này, vì chúng dựng `_Snap` trực tiếp và bỏ qua bước tính `ema20_prev3`.

### 2. `if long_regime … elif short_regime`

Với `elif`, SHORT **không bao giờ được xét** mỗi khi có regime LONG trong 3 nến trước, kể cả khi LONG không phát tín hiệu. Brief định nghĩa hai chiều độc lập với nhau.
- **Sửa:** đổi thành `if pending is None and short_regime …`.
- Không thêm test riêng cho chỗ này. Dựng một kịch bản regime LONG và SHORT cùng nằm trong 3 nến liên tiếp tốn công hơn nhiều so với rủi ro. Tác động thực tế nằm trong lần đo lại dưới đây.

### 3. Đo lại sau khi sửa (`--skip-null`, EXIT=0)

| baseline | Lần vào | net_after_funding | PF | Trước khi sửa |
|---|---:|---:|---:|---|
| CHÍNH 2020–2023 | 41 | **−23,96** | 0,60 | 42 lần vào, −19,20 |
| LẶP LẠI 2024–2026 | 47 | **−32,96** | 0,51 | không đổi |

Tiêu chí (1) đạt, (2) hỏng, (4) hỏng. Đối chứng ngẫu nhiên được bỏ qua đúng theo §2.6.

### 4. Những điểm đã kiểm và đúng

- **Profile:** dùng nến 5m của D-1, được khoá theo ngày D. `VAH`/`VAL` trong `regime(x)` lấy theo ngày của nến `x`, vì mỗi `_Snap` lưu profile của chính nó.
- **Thứ tự thoát lệnh:** SL/BE, rồi TP1, rồi TP2/EMA20, rồi TIME. BE áp dụng từ nến `j+1`; TP2 không xét trong cùng nến với TP1.
- **Lệnh chờ:** hết hạn đúng sau `t+2`.
- **Bộ lọc vùng cản:** biểu thức `and/or` đúng thứ tự ưu tiên của Python.
- **`# noqa: B023` cho `pos_would_liquidate`:** hợp lý. `_close_leg` chỉ được gọi trong cùng vòng lặp, và cờ này có thể bật sau khi hàm được định nghĩa, nên phải đọc giá trị sống. Việc truyền trạng thái bằng tham số mặc định trong một hàm lồng thì khó đọc, nhưng đúng. Không refactor thêm, vì đây là mã đo một lần.
