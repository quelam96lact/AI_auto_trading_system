# Brief đợt 137 — diễn tập so với BẢN KÊ SỐ DÒNG chụp lúc dump, không so với nguồn đang sống

Đợt 136 làm đúng brief. Nhưng lần diễn tập thật đầu tiên (Claude chạy, 30/09 20:09) cho thấy **quy
tắc so số dòng trong brief 136 — do Claude viết — sai về cấu trúc**. Đợt này sửa nó, cộng hai việc nhỏ.

## Giới hạn

- **KHÔNG commit, KHÔNG push.** Không tạo scheduled task. Không restart/rebuild container. Không sửa
  `.env`, `docker-compose.yml`, `scripts/verify_backup_restore.py`.
- **Không chạy `restore_drill.py` thật** (nó tạo/xoá database). Claude chạy lần thật.
- **Được phép** chạy `scripts/sched.sh backup` **đúng một lần** để có một bản kê thật đi kèm dump thật
  (đó là job sao lưu hằng đêm, chỉ đọc DB). Không chạy lần thứ hai; không xoá file sao lưu nào bằng tay.
- GitNexus: `impact` trước khi sửa symbol, `detect_changes` sau khi sửa. Index cũ → `npx gitnexus
  analyze`, ghi rõ trong báo cáo.

## Việc 1 — bản kê số dòng lúc dump

### Vì sao — số đo thật, dán lại nguyên văn

Chạy trên bản dump **TỐT**, 18 giờ sau khi dump:

```
[CRITICAL] Bảng account_nav_snapshot phục hồi thiếu dòng: nguồn=11,407, phục hồi=11,013 (96.55% < 99%)
... (6 bảng snapshot tài khoản, đều khoảng 96,5%)
```

Các bảng snapshot tài khoản được ghi **24/7** (`account_nav_snapshot` 22 dòng/giờ; riêng khung
02:00–04:00 Chủ nhật 27/09 có 48 dòng). Nên so với nguồn đang sống thì:
- kết quả **phụ thuộc giờ chạy**: task chạy bù trễ vài giờ là báo oan, bảng nhỏ/mới hỏng sớm hơn;
- băng 1% trên bảng lớn lại **để lọt** mất mát dưới 1% (`bars`: khoảng 9.000 dòng).

### Thiết kế

1. `scripts/backup_db.sh`: **ngay trước** `pg_dump`, ghi bản kê `trading_${TIMESTAMP}.counts` cạnh
   file `.dump`. Mỗi dòng `ten_bang<TAB>so_dong`, cho **mọi** bảng `relkind IN ('r','p')` trong schema
   `public`. Liệt kê từ catalog, **không** dùng danh sách viết cứng — cùng truy vấn với
   `LIST_TABLES_SQL` của `restore_drill.py`.
   - Dump hỏng hoặc xác minh `pg_restore -l` hỏng → **xoá luôn bản kê** của lần đó. Bản kê không có
     dump đi kèm là rác gây hiểu nhầm.
   - Ghi ra file tạm rồi đổi tên. Không bao giờ để lại một bản kê viết dở.
   - Dòng dọn bản cũ (`find ... -mtime`) phải dọn **cả `trading_*.counts`**. Nếu không, bản kê sẽ tích
     mãi trên đĩa VPS.
2. `scripts/restore_drill.py`:
   - Đọc bản kê **cùng tên gốc** với dump được diễn tập. Không có hoặc đọc không được → **CRITICAL**
     "không có bản kê cho <tên dump>". **Tuyệt đối không rơi về so với nguồn đang sống**: đường lui
     đó chính là lỗi đang sửa, và nó sẽ lặng lẽ bật lại.
   - Tập bảng: **lấy từ bản kê** thay vì truy vấn DB nguồn. Bảng có trong bản kê mà thiếu ở bản phục
     hồi → CRITICAL nêu tên (giữ nguyên `judge_tables`).
   - Quy tắc số dòng mới: **`phuc_hoi >= ban_ke` — không có băng dung sai.** Lý do: bản kê chụp
     *trước* snapshot của `pg_dump`, nên trong mấy giây giữa hai mốc chỉ có dòng được **thêm**, bản
     phục hồi chỉ có thể nhiều hơn hoặc bằng.
     - Tiền đề phải kiểm, đừng tin brief: **không job định kỳ nào xoá dòng**. Claude đã đo:
       `timescaledb_information.jobs` chỉ có `policy_telemetry` và `policy_job_stat_history_retention`
       (không có retention trên bảng dữ liệu). Các lệnh `DELETE` trong code chỉ nằm ở script chạy tay:
       `merge_bars_daily_chunks.py`, `build_derivative_continuous_series.py`, `.probe_event_loop_block.py`.
       Agent tự chạy lại hai phép đo này và **dán kết quả**. Nếu thấy một job định kỳ có xoá dòng thì
       **dừng lại và báo**, đừng tự nới dung sai.
   - `-1` ở bất kỳ bên nào vẫn là CRITICAL, **không bao giờ** là "khớp". Giữ `COUNT_FAILED`.
   - Xoá `MIN_RATIO` và mọi chú thích nói về băng 99% hay lý do chọn Chủ nhật. Thay bằng chú thích
     giải thích bản kê và dẫn số đo ở trên.
   - Sau khi đổi, diễn tập **không còn đếm số dòng trên database `trading` nữa**. Chỉ còn kiểm
     "`trading` vẫn tồn tại" sau khi dọn.
3. `DEPLOYMENT.md`: sửa đúng các đoạn đợt 136 đã viết về băng 99% và lý do chọn Chủ nhật. Giờ chạy
   Chủ nhật 04:00 **giữ nguyên** (sau backup, ít tải), nhưng lý do đổi thành "ít tải". Cập nhật mô tả
   `backup_db.sh` để nêu bản kê `.counts`. Không sửa chỗ khác.

### Tiêu chí hoàn thành

1. `bash -n scripts/backup_db.sh` sạch. Chạy `scripts/sched.sh backup` **một lần**. Dán `ls -l` của
   cặp `.dump` + `.counts` mới, số dòng của `.counts`, và 5 dòng đầu. Số bảng trong bản kê phải
   bằng số bảng mà `LIST_TABLES_SQL` trả trên `trading`; dán cả hai con số.
2. Test `backup_db.sh` bằng lệnh `docker` giả trên PATH, theo cách test shell sẵn có trong repo (tìm
   xem có chưa; chưa có thì báo lại, đừng dựng một khung test lớn):
   - dump hỏng → **không** còn `.counts`;
   - `.counts` cũ hơn hạn dọn → bị xoá.
3. `tests/test_restore_drill.py`:
   - bản phục hồi **bằng** bản kê → IM;
   - **nhiều hơn** (có dòng thêm sau khi chụp) → IM;
   - **ít hơn đúng 1 dòng** → BÁO nêu tên bảng và hai số;
   - không có bản kê → BÁO, và `runner` **không** nhận lệnh `CREATE DATABASE` nào (kiểm trước khi đụng DB);
   - bản kê có dòng hỏng (không phải `ten<TAB>so`) → BÁO, không bỏ qua dòng đó;
   - `runner` **không** nhận lệnh đếm nào trên database `trading`.
4. **Lỗ test đợt 136 — Claude đã phá thử:** bỏ nhánh `rc != 0` trong `judge_pg_restore` mà **39/39
   vẫn xanh**. Mọi ca hỏng trong test đều kèm `error:` ở stderr. Thêm test cho **exit 137 với stderr
   rỗng** (pg_restore bị giết vì hết bộ nhớ — container này từng có tiền sử OOM). Test đó phải đỏ
   khi làm lại đúng phá thử trên.
5. Phá thử, ghi nguyên văn dòng đỏ, khôi phục và đối chiếu hash:
   - Đổi `>=` thành băng 99% cũ → ca "ít hơn đúng 1 dòng" phải đỏ.
   - Cho thiếu bản kê thì rơi về so với nguồn sống → ca "không có bản kê" phải đỏ.
6. `ruff` sạch; `uv run pytest -q` ≥ **1.593 passed** cộng số test mới; `test_deployment_doc.py` xanh.

## Việc 2 — dòng `host-preflight` trong `sched.sh`

Dòng `exec "$RUN" host-preflight.log host-preflight       uv run python ...` bị mất dấu `\` xuống
dòng từ đợt 133. Nó vẫn chạy đúng; tách lại thành hai dòng như các nhánh khác. Kiểm bằng `bash -n
scripts/sched.sh` cùng một lần `scripts/sched.sh host-preflight` thật, kỳ vọng **6 ĐẠT / 0 HỎNG / 8
BỎ QUA**.

## Báo cáo

`docs/superpowers/research/2026-09-30-dot-137-ban-ke-so-dong.md`:

- Số đo dán nguyên văn.
- Brief sai hoặc tự mâu thuẫn ở đâu thì nói ra — đợt 135 và 136 agent đều bắt được lỗi của brief.
- Cái gì không kiểm được thì ghi là **không kiểm được**. Đặc biệt: đường diễn tập thật với bản kê
  **chưa chạy**, Claude sẽ chạy.
