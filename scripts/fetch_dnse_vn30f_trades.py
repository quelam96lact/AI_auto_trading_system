"""Script tải và chuẩn hoá dữ liệu khớp lệnh DNSE phái sinh VN30F (Brief đợt 186).

Chức năng:
1. Xác định hợp đồng front-month theo ngày (`front_month_symbol`).
2. Tải và phân trang từng phiên giao dịch từ DNSE Open API (`fetch_session_trades`).
3. Đánh giá tính liên tục của khối lượng phiên (`volume_continuity`).
4. Ghi file dạng gzip JSONL `<out>/<mã>/<ngày>.jsonl.gz` và ghi manifest.
5. Kiểm tra toàn vẹn file với cờ `--verify`.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any

# Ép mã hoá UTF-8 trên Windows để tránh lỗi UnicodeEncodeError
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream and getattr(_stream, "encoding", None) and _stream.encoding.lower() not in ("utf-8", "utf8"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._db_common import load_dotenv
from scripts.measure_derivative_contract_volume import (
    filter_living_contracts,
    identify_front_month,
)
from scripts.record_vn30f_orderbook import generate_vn30_candidate_contracts
from scripts.screen_vn30f_orderbook import IS_START_DATE
from trading.calendar_vn import TZ

__all__ = [
    "MAX_MISSING_CONTINUOUS_RATIO",
    "fetch_session_trades",
    "front_month_symbol",
    "main",
    "parse_trade_second",
    "parse_trade_time",
    "save_session_trades",
    "volume_continuity",
]

MAX_MISSING_CONTINUOUS_RATIO: float = 0.005  # 0.5%


def front_month_symbol(d: date) -> str:
    """Xác định mã hợp đồng front-month VN30F tại ngày d (chuẩn HNX, e.g. 41I1G4000).

    Tái sử dụng generate_vn30_candidate_contracts và identify_front_month.
    """
    candidates = generate_vn30_candidate_contracts(d)
    living = filter_living_contracts(candidates, d)
    front = identify_front_month(living, d)
    if front is None:
        raise ValueError(f"Không tìm thấy hợp đồng front-month VN30F cho ngày {d}")
    return front.symbol


def parse_trade_time(t_val: Any) -> datetime:
    """Chuyển đổi trường thời gian của lệnh sang datetime có tzinfo=TZ."""
    if isinstance(t_val, datetime):
        if t_val.tzinfo is None:
            return t_val.replace(tzinfo=TZ)
        return t_val.astimezone(TZ)
    if isinstance(t_val, (int, float)):
        return datetime.fromtimestamp(float(t_val), tz=TZ)
    s = str(t_val).strip()
    if s.isdigit():
        return datetime.fromtimestamp(int(s), tz=TZ)
    s = s.replace("T", " ")
    s_core = s[:19]
    try:
        dt = datetime.strptime(s_core, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=TZ)
    except ValueError:
        dt = datetime.strptime(s_core, "%Y-%m-%d")
        return dt.replace(tzinfo=TZ)


def parse_trade_second(t_val: Any) -> int:
    """Lấy epoch giây (floor) từ trường thời gian của lệnh."""
    dt = parse_trade_time(t_val)
    return int(dt.timestamp())


def volume_continuity(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Tính tính liên tục của khối lượng phiên: total_volume, missing_continuous, missing_outside.

    Khoảng thiếu ở dòng i là tv[i] - tv[i-1] - qtty[i] (với i=0 thì tv[-1]=0).
    Cộng vào missing_continuous khi dòng i-1 có giờ >= 09:00:00 VÀ dòng i có giờ < 14:30:00.
    Mọi khoảng thiếu khác (gồm khoảng thiếu ở dòng đầu ATO) cộng vào missing_outside.
    """
    if not rows:
        return {
            "total_volume": 0,
            "missing_continuous": 0,
            "missing_outside": 0,
        }

    total_volume = int(rows[-1].get("total_volume_traded", 0))
    missing_continuous = 0
    missing_outside = 0

    # Dòng đầu tiên (i = 0)
    tv_0 = int(rows[0].get("total_volume_traded", 0))
    q_0 = int(rows[0].get("match_qtty", 0))
    gap_0 = tv_0 - q_0
    if gap_0 > 0:
        missing_outside += gap_0

    # Các dòng tiếp theo (i >= 1)
    for i in range(1, len(rows)):
        tv_curr = int(rows[i].get("total_volume_traded", 0))
        tv_prev = int(rows[i - 1].get("total_volume_traded", 0))
        q_curr = int(rows[i].get("match_qtty", 0))
        gap = tv_curr - tv_prev - q_curr
        if gap > 0:
            t_prev = parse_trade_time(rows[i - 1].get("time"))
            t_curr = parse_trade_time(rows[i].get("time"))
            if t_prev.time() >= dt_time(9, 0, 0) and t_curr.time() < dt_time(14, 30, 0):
                missing_continuous += gap
            else:
                missing_outside += gap

    return {
        "total_volume": total_volume,
        "missing_continuous": missing_continuous,
        "missing_outside": missing_outside,
    }


def fetch_session_trades(
    client: Any,
    symbol: str,
    d: date,
    sleep_fn: Callable[[float], Any] = time.sleep,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Tải và phân trang dữ liệu khớp lệnh phiên d từ DNSE API.

    Khung from=08:30:00, to=15:05:00 giờ VN.
    Lật trang bằng to = floor(giây cũ nhất của trang) + 1. Khử trùng lặp theo total_volume_traded.
    Nếu một trang không thêm lệnh mới nào (hơn 1000 lệnh trong một giây) thì to = giây đó và tăng stuck_seconds.
    Dừng khi trang có < 1000 lệnh, khi to <= from, hoặc khi vượt 3000 lần gọi.
    """
    dt_from = datetime.combine(d, dt_time(8, 30, 0), tzinfo=TZ)
    dt_to = datetime.combine(d, dt_time(15, 5, 0), tzinfo=TZ)
    cur_from = int(dt_from.timestamp())
    cur_to = int(dt_to.timestamp())

    board_id = getattr(client, "board_id", None)
    if board_id is None:
        try:
            from dnse import BoardId
            board_id = BoardId.ROUND_LOT
        except Exception:
            board_id = "G1"

    collected_trades: dict[Any, dict[str, Any]] = {}
    stuck_seconds = 0
    calls = 0

    while calls < 3000 and cur_to > cur_from:
        calls += 1
        raw_items: list[Any] = []
        max_retries = 5
        for attempt in range(1, max_retries + 1):
            try:
                try:
                    raw_items = client.market.trades(
                        symbol,
                        board_id,
                        from_ts=str(cur_from),
                        to_ts=str(cur_to),
                        limit=1000,
                    )
                except TypeError:
                    raw_items = client.market.trades(
                        symbol,
                        board_id,
                        str(cur_from),
                        str(cur_to),
                        limit=1000,
                    )
                break
            except Exception:
                if attempt == max_retries:
                    raise
                sleep_fn(30.0 * attempt)

        sleep_fn(1.1)

        if not raw_items:
            break

        page_rows: list[dict[str, Any]] = []
        for item in raw_items:
            if hasattr(item, "model_dump"):
                r = item.model_dump(mode="json", exclude_none=True)
            elif isinstance(item, dict):
                r = dict(item)
            else:
                r = dict(item)
            page_rows.append(r)

        oldest_sec = min(parse_trade_second(r.get("time")) for r in page_rows)

        prev_count = len(collected_trades)
        for r in page_rows:
            tv = r.get("total_volume_traded")
            if tv is not None:
                collected_trades[tv] = r
            else:
                collected_trades[id(r)] = r
        new_count = len(collected_trades)

        if new_count == prev_count:
            # Bị kẹt > 1000 lệnh trong cùng một giây
            cur_to = oldest_sec
            stuck_seconds += 1
        else:
            cur_to = oldest_sec + 1

        if len(page_rows) < 1000:
            break

    # Sắp xếp các dòng theo total_volume_traded tăng dần
    rows = sorted(collected_trades.values(), key=lambda r: int(r.get("total_volume_traded", 0)))
    continuity = volume_continuity(rows)

    info = {
        "date": d.isoformat(),
        "symbol": symbol,
        "n_trades": len(rows),
        "total_volume": continuity["total_volume"],
        "missing_continuous": continuity["missing_continuous"],
        "missing_outside": continuity["missing_outside"],
        "stuck_seconds": stuck_seconds,
        "calls": calls,
    }
    return rows, info


def save_session_trades(
    out_dir: Path | str,
    symbol: str,
    d: date,
    rows: list[dict[str, Any]],
    info: dict[str, Any],
) -> Path | None:
    """Ghi dữ liệu phiên vào <out>/<mã>/<ngày>.jsonl.gz qua file .tmp và thêm dòng vào _manifest.jsonl."""
    p_out = Path(out_dir)
    target_dir = p_out / symbol
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{d.isoformat()}.jsonl.gz"
    tmp_file = target_dir / f"{d.isoformat()}.jsonl.gz.tmp"

    if target_file.exists():
        return target_file

    if not rows:
        # Ngày nghỉ lễ / không có giao dịch: không ghi file .gz, chỉ ghi manifest n_trades: 0
        _append_manifest(p_out, info)
        return None

    try:
        with gzip.open(tmp_file, "wt", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp_file, target_file)
    finally:
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except OSError:
                pass

    _append_manifest(p_out, info)
    return target_file


def _append_manifest(out_dir: Path, info: dict[str, Any]) -> None:
    manifest_file = out_dir / "_manifest.jsonl"
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    with manifest_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(info, ensure_ascii=False) + "\n")


def verify_data_dir(out_dir: Path | str) -> int:
    """Xác thực toàn bộ các file .jsonl.gz trong out_dir, in bảng continuity và trả về 1 nếu có phiên lỗi > 0.5%."""
    p_out = Path(out_dir)
    if not p_out.exists():
        print(f"[VERIFY] Thư mục '{out_dir}' không tồn tại.", file=sys.stderr)
        return 0

    files = sorted(p_out.glob("*/*.jsonl.gz"))
    if not files:
        print(f"[VERIFY] Không tìm thấy file .jsonl.gz nào trong '{out_dir}'.")
        return 0

    print("=" * 96)
    print(f"{'Ngày':<12} {'Mã':<12} {'Số lệnh':>10} {'Tổng KL':>10} {'Thiếu LT':>10} {'Thiếu ngoài':>12} {'Tỉ lệ LT':>10} {'Trạng thái':>12}")
    print("-" * 96)

    has_violation = False
    for fpath in files:
        symbol = fpath.parent.name
        date_str = fpath.name.replace(".jsonl.gz", "")
        try:
            with gzip.open(fpath, "rt", encoding="utf-8") as f:
                rows = [json.loads(line) for line in f if line.strip()]
            cont = volume_continuity(rows)
            tot = cont["total_volume"]
            m_cont = cont["missing_continuous"]
            m_out = cont["missing_outside"]
            ratio = (m_cont / tot) if tot > 0 else 0.0
            status = "LỖI (>0.5%)" if ratio > MAX_MISSING_CONTINUOUS_RATIO else "ĐẠT"
            if ratio > MAX_MISSING_CONTINUOUS_RATIO:
                has_violation = True
            print(
                f"{date_str:<12} {symbol:<12} {len(rows):>10} {tot:>10} {m_cont:>10} {m_out:>12} {ratio*100:>9.2f}% {status:>12}"
            )
        except Exception as exc:
            has_violation = True
            print(f"{date_str:<12} {symbol:<12} {'-':>10} {'-':>10} {'-':>10} {'-':>12} {'-':>10} {f'HỎNG: {exc}':>12}")

    print("=" * 96)
    return 1 if has_violation else 0


def create_dnse_client(api_key: str, api_secret: str) -> Any:
    """Hàm tạo client DNSE. Chỉ import dnse bên trong hàm này."""
    from dnse import DnseClient
    return DnseClient(api_key=api_key, api_secret=api_secret)


def main(
    args: Sequence[str] | None = None,
    client_factory: Callable[[str, str], Any] | None = None,
    sleep_fn: Callable[[float], Any] = time.sleep,
) -> int:
    parser = argparse.ArgumentParser(
        description="Script tải và chuẩn hoá dữ liệu khớp lệnh DNSE phái sinh VN30F (Brief 186)"
    )
    parser.add_argument("--from", dest="from_date", help="Ngày bắt đầu (YYYY-MM-DD)")
    parser.add_argument("--to", dest="to_date", help="Ngày kết thúc (YYYY-MM-DD)")
    parser.add_argument("--out", default="data/dnse_trades", help="Thư mục lưu dữ liệu (mặc định: data/dnse_trades)")
    parser.add_argument("--verify", action="store_true", help="Kiểm tra lại dữ liệu đã tải trong --out mà không gọi mạng")

    effective_args = sys.argv[1:] if args is None else list(args)
    parsed_args = parser.parse_args(effective_args)

    if parsed_args.verify:
        return verify_data_dir(parsed_args.out)

    if not parsed_args.from_date or not parsed_args.to_date:
        parser.error("Cần chỉ định cả --from và --to khi không dùng --verify")

    d_start = date.fromisoformat(parsed_args.from_date)
    d_end = date.fromisoformat(parsed_args.to_date)

    if d_start > d_end:
        print(f"Lỗi: --from ({d_start}) lớn hơn --to ({d_end})", file=sys.stderr)
        return 2

    # Ràng buộc bất biến: Từ chối nếu --to >= IS_START_DATE (2026-09-25)
    if d_end >= IS_START_DATE:
        print(
            f"[BẢO VỆ CHỐNG NHÌN TRƯỚC] Từ chối: --to ({d_end}) >= IS_START_DATE ({IS_START_DATE}). "
            f"Không được phép mở dữ liệu từ ngày 2026-09-25.",
            file=sys.stderr,
        )
        return 2

    load_dotenv()
    api_key = os.environ.get("PRODUCT_DNSE_API_Key", "")
    api_secret = os.environ.get("PRODUCT_DNSE_API_Secret", "")

    if client_factory is not None:
        client = client_factory(api_key, api_secret)
    else:
        client = create_dnse_client(api_key, api_secret)

    out_path = Path(parsed_args.out)
    curr_date = d_start
    while curr_date <= d_end:
        # Chỉ tải các ngày thứ Hai đến thứ Sáu
        if curr_date.weekday() < 5:
            sym = front_month_symbol(curr_date)
            target_file = out_path / sym / f"{curr_date.isoformat()}.jsonl.gz"
            if target_file.exists():
                print(f"[{curr_date}] Đã có file {target_file}, bỏ qua.")
            else:
                print(f"[{curr_date}] Đang tải dữ liệu {sym}...")
                rows, info = fetch_session_trades(client, sym, curr_date, sleep_fn=sleep_fn)
                save_session_trades(out_path, sym, curr_date, rows, info)
                print(f"[{curr_date}] Hoàn tất: {len(rows)} lệnh, total_volume={info['total_volume']}")
        curr_date += timedelta(days=1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
