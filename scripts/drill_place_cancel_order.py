"""Làm mới công cụ diễn tập 'đặt rồi huỷ một lệnh thật' (T3) — Brief đợt 100.

Mục đích:
Kiểm chứng chu trình kết nối, xác thực token qua DB, ký lệnh bằng RSA private key,
đặt lệnh giới hạn mua (LO BUY) xa giá thị trường và huỷ ngay lập tức trên sàn thật.

⛔ LUẬT TỐI THƯỢNG:
- Agent TUYỆT ĐỐI KHÔNG gửi bất kỳ lệnh thật nào lên sàn.
- Script chỉ gửi lệnh thật khi có cờ --send VÀ người vận hành gõ chính xác "YES".
- Không có cờ --send: chỉ CHẠY THỬ (dry-run, chỉ đọc dữ liệu), không gọi đặt hay huỷ lệnh.

Cách chạy:
  Chạy thử (chỉ đọc):
    uv run python scripts/drill_place_cancel_order.py --account 0434221 --symbol VCB

  Chạy thật (chủ tài khoản trực tiếp thực thi trong phiên sống):
    uv run python scripts/drill_place_cancel_order.py --account 0434221 --symbol VCB --send
"""

import argparse
import asyncio
import dataclasses
import json
import math
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from ssi_sdk import AsyncData, AsyncTrading
from ssi_sdk.enums import OrderSide

from trading.alerts import alert
from trading.calendar_vn import TZ
from trading.collector.ssi_auth import ensure_authenticated
from trading.config import Config, load_config
from trading.ssi_orders import fetch_order_history
from trading.storage.db import Storage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LOGS_DIR = Path("logs")
STATUS_POLL_ATTEMPTS = 3
STATUS_POLL_SLEEP_SEC = 2.0


def _fail_loud(alert_fn, headline: str, account: str, symbol: str, price, placed, detail) -> None:
    """In khoi CANH BAO NGHIEM TRONG, ban alert CRITICAL, thoat ma 2.

    Mot cho duy nhat cho moi ca 'tien that co the dang o trang thai khong ro'
    (dat loi, huy loi, huy chua xac nhan) - audit dot 100."""
    block = (
        "\n" + "!" * 80 + "\n"
        " CẢNH BÁO NGHIÊM TRỌNG!\n"
        f" {headline}\n"
        f"  - Tài khoản:          {account}\n"
        f"  - Mã cổ phiếu:        {symbol}\n"
        f"  - Giá đặt:            {price:,.0f} VNĐ\n"
        f"  - Số lượng:           100 cổ phiếu\n"
        f"  - Order ID:           {getattr(placed, 'order_id', 'N/A')}\n"
        f"  - Client Request ID:  {getattr(placed, 'client_request_id', 'N/A')}\n"
        f"  - Chi tiết:           {detail}\n"
        + "!" * 80 + "\n"
    )
    print(block, file=sys.stderr)
    t = alert_fn(
        "CRITICAL",
        f"drill T3: {headline}",
        account=account,
        symbol=symbol,
        price=price,
        order_id=getattr(placed, "order_id", "N/A"),
        client_request_id=getattr(placed, "client_request_id", "N/A"),
        error=str(detail),
    )
    if t is not None:
        t.join(timeout=6)
    sys.exit(2)


def get_tick_size(price: float, exchange: str) -> int:
    """Xác định đơn vị yết giá (bước giá) theo mức giá và sàn giao dịch.

    Nguồn pháp lý & quy chế chính thức:
    - HOSE: Quyết định số 17/QĐ-SGDHCM ban hành Quy chế giao dịch chứng khoán
      niêm yết tại Sở Giao dịch Chứng khoán TP.HCM (Điều 5 - Đơn vị yết giá):
      + Mức giá < 10.000 VNĐ: đơn vị yết giá là 10 VNĐ.
      + Mức giá từ 10.000 đến 49.950 VNĐ: đơn vị yết giá là 50 VNĐ.
      + Mức giá >= 50.000 VNĐ: đơn vị yết giá là 100 VNĐ.
    - HNX: Quyết định số 639/QĐ-SGDHN ban hành Quy chế giao dịch chứng khoán
      niêm yết tại Sở Giao dịch Chứng khoán Hà Nội (Điều 4):
      + Đơn vị yết giá đối với cổ phiếu niêm yết là 100 VNĐ (cho mọi mức giá).
    """
    exch = exchange.upper().strip()
    if exch == "HNX":
        return 100
    if price < 10_000:
        return 10
    if price < 50_000:
        return 50
    return 100


def ceil_to_tick(val: float, tick_or_exchange: int | str) -> int:
    """Làm tròn LÊN theo bước giá: math.ceil(val / tick) * tick."""
    if isinstance(tick_or_exchange, str):
        tick = get_tick_size(val, tick_or_exchange)
    else:
        tick = int(tick_or_exchange)
    return int(math.ceil(val / tick) * tick)


def calculate_drill_order_levels(ref: float, exchange: str) -> tuple[int, int]:
    """Tính giá sàn và giá đặt LO BUY an toàn cho diễn tập.

    Quy tắc:
    - Biên độ: HOSE = 7% (band = 0.07), HNX = 10% (band = 0.10).
    - Giá sàn (floor): làm tròn LÊN bước giá: ceil_to_tick(ref * (1 - band)).
    - Giá đặt (price): ceil_to_tick(ref * (1 - band + 0.01)), cao hơn sàn khoảng 1%
      nhưng vẫn cách tham chiếu ~6% (HOSE) hoặc ~9% (HNX), gần như chắc chắn
      không khớp trong vài giây trước khi huỷ.
    - Ràng buộc an toàn: floor <= price < ref.

    Trả về: (floor, price)
    """
    exch = exchange.upper().strip()
    if exch == "HOSE":
        band = 0.07
    elif exch == "HNX":
        band = 0.10
    else:
        raise ValueError(f"Sàn '{exchange}' không được hỗ trợ. Chỉ nhận HOSE hoặc HNX.")

    raw_floor = ref * (1.0 - band)
    tick_floor = get_tick_size(raw_floor, exch)
    floor = ceil_to_tick(raw_floor, tick_floor)

    raw_price = ref * (1.0 - band + 0.01)
    tick_price = get_tick_size(raw_price, exch)
    price = ceil_to_tick(raw_price, tick_price)

    if not (floor <= price < ref):
        raise ValueError(
            f"Giá tính toán vi phạm ràng buộc an toàn (floor <= price < ref): "
            f"floor={floor}, price={price}, ref={ref}"
        )
    return floor, price


def drill_price(ref: float, exchange: str) -> int:
    """Tính giá đặt LO BUY diễn tập từ giá tham chiếu và sàn giao dịch."""
    _, price = calculate_drill_order_levels(ref, exchange)
    return price


def _parse_row_date(val: str | date | datetime) -> date:
    """Phân tích ngày từ dữ liệu nến thô của SSI."""
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if " " in s:
        s = s.split(" ")[0]
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Không thể phân tích ngày từ '{val}'")


def select_reference_price(rows: list, today_vn: date | None = None) -> float:
    """Chọn giá tham chiếu từ nến ngày thô của SSI.

    Giá tham chiếu = giá đóng cửa của phiên gần nhất có ngày NHỎ HƠN hôm nay (giờ VN).
    Không dùng nến hôm nay (nếu có) vì trong phiên nến hôm nay là giá khớp hiện tại.
    """
    if today_vn is None:
        today_vn = datetime.now(TZ).date()

    valid_rows = []
    for r in rows:
        d = _parse_row_date(r.trading_date)
        if d < today_vn:
            valid_rows.append((d, float(r.close_price)))

    if not valid_rows:
        raise ValueError(f"Không tìm thấy phiên giao dịch nào trước ngày {today_vn}")

    valid_rows.sort(key=lambda x: x[0])
    return valid_rows[-1][1]


def get_exchange(storage: Storage, symbol: str) -> str | None:
    """Tra cứu sàn giao dịch của mã từ bảng symbol_universe."""
    with storage.conn() as c:
        row = c.execute(
            "SELECT exchange FROM symbol_universe WHERE symbol = %s",
            (symbol.upper().strip(),),
        ).fetchone()
    if row and row[0]:
        return str(row[0]).strip().upper()
    return None


async def run_drill(
    account: str,
    symbol: str = "VCB",
    send: bool = False,
    cfg: Config | None = None,
    storage: Storage | None = None,
    trading_client=None,
    data_client=None,
    input_fn=input,
    get_exchange_fn=None,
    get_ref_fn=None,
    alert_fn=alert,
    sleep_fn=asyncio.sleep,
) -> int:
    """Thực thi quy trình diễn tập đặt và huỷ một lệnh thật.

    Hỗ trợ tiêm phụ thuộc (dependency injection) cho unit test:
    - trading_client, data_client: client giả lập SSI SDK
    - input_fn: hàm nhận xác nhận (mặc định input)
    - get_exchange_fn: hàm tra cứu sàn
    - get_ref_fn: hàm tra cứu giá tham chiếu
    - alert_fn: hàm phát alert
    """
    symbol = symbol.upper().strip()

    # Bước 0: Kiểm tra tham số bắt buộc --account trước khi gọi mạng/DB
    if not account or not account.strip():
        print("!! LỖI: Tham số --account là bắt buộc (không có mặc định).", file=sys.stderr)
        sys.exit(2)
    account = account.strip()

    # Bước 1 & 2: Tra cứu sàn giao dịch
    if get_exchange_fn is not None:
        exchange = get_exchange_fn(symbol)
    else:
        if storage is None:
            raise RuntimeError("Cần Storage để tra cứu sàn giao dịch từ DB.")
        exchange = get_exchange(storage, symbol)

    if not exchange or exchange not in ("HOSE", "HNX"):
        print(
            f"!! DỪNG — mã {symbol} thuộc sàn '{exchange or 'KHÔNG RÕ'}'. "
            "Chỉ hỗ trợ HOSE hoặc HNX (UPCOM tính giá tham chiếu theo bình quân gia quyền).",
            file=sys.stderr,
        )
        sys.exit(1)

    auth_created = None
    try:
        # Khởi tạo client nếu chưa được tiêm
        if trading_client is None or data_client is None:
            if cfg is None or storage is None:
                raise RuntimeError("Cần Config và Storage để xác thực SSI.")
            auth_created = await ensure_authenticated(cfg, storage)
            auth_created.config.private_key = cfg.ssi_private_key
            if trading_client is None:
                trading_client = AsyncTrading(auth_created)
            if data_client is None:
                data_client = AsyncData(auth_created)

        # Bước 3: Kiểm tra sức mua (chỉ đọc)
        mbs = await trading_client.trading.get_max_buy_sell_at_market_price(account, symbol)
        max_buy = getattr(mbs, "max_buy_quantity", 0)
        if max_buy < 100:
            missing = 100 - max_buy
            if send:
                print(
                    f"!! DỪNG — sức mua thật ({max_buy} cổ phiếu) < 100 cổ phiếu tối thiểu "
                    f"(thiếu {missing} cổ phiếu). KHÔNG đặt lệnh chắc chắn thất bại.",
                    file=sys.stderr,
                )
                sys.exit(1)
            else:
                print(
                    f"!! CẢNH BÁO SỨC MUA: sức mua thật ({max_buy} cổ phiếu) < 100 cổ phiếu tối thiểu "
                    f"(thiếu {missing} cổ phiếu). Nếu chạy thật có --send sẽ bị DỪNG.\n"
                    "Tiếp tục chạy thử (dry-run) để kiểm tra giá tham chiếu và lập kế hoạch lệnh...",
                    file=sys.stderr,
                )

        # Bước 4: Lấy giá tham chiếu (chỉ đọc)
        if get_ref_fn is not None:
            ref = float(get_ref_fn(symbol))
        else:
            today_vn = datetime.now(TZ).date()
            from_date = (today_vn - timedelta(days=14)).strftime("%Y/%m/%d") + " 00:00:00"
            to_date = today_vn.strftime("%Y/%m/%d") + " 23:59:59"
            rows = await data_client.market_data.get_ohlc_1day_historical(
                symbol, from_date, to_date
            )
            if not rows:
                print(
                    f"!! DỪNG — không lấy được dữ liệu nến ngày từ SSI cho mã {symbol}.",
                    file=sys.stderr,
                )
                sys.exit(1)
            ref = select_reference_price(rows, today_vn)

        # Bước 5: Tính giá đặt LO an toàn
        floor, price = calculate_drill_order_levels(ref, exchange)

        # Bước 6: In kế hoạch lệnh
        print("\n" + "=" * 65)
        print(" KẾ HOẠCH LỆNH DIỄN TẬP ĐẶT-HUỶ (T3 DRILL ORDER PLAN)")
        print("=" * 65)
        print(f" Tài khoản:        {account}")
        print(f" Mã cổ phiếu:      {symbol}")
        print(f" Sàn giao dịch:    {exchange}")
        print(f" Giá tham chiếu:   {ref:,.0f} VNĐ")
        print(f" Giá sàn:          {floor:,.0f} VNĐ")
        print(f" Giá đặt (LO BUY): {price:,.0f} VNĐ (thấp hơn ref ~{((ref-price)/ref)*100:.1f}%)")
        print(" Khối lượng đặt:   100 cổ phiếu (01 lô tối thiểu)")
        print(f" Sức mua tối đa:   {max_buy:,} cổ phiếu")
        print("=" * 65)

        if not send:
            print("[CHẠY THỬ] không gửi lệnh. (Dùng cờ --send để kích hoạt gửi lệnh thật)")
            sys.exit(0)

        # Bước 7: Xác nhận gõ YES nếu có --send
        confirm_input = input_fn("Gõ YES để GỬI LỆNH THẬT: ")
        if confirm_input != "YES":
            print(
                f"Đã huỷ diễn tập (nhận được '{confirm_input}', yêu cầu chính xác 'YES'). Thoát an toàn."
            )
            sys.exit(0)

        # Bước 8: Đặt lệnh thật
        print(f"\nBước 8: Đặt lệnh LIMIT BUY 100 {symbol} @ {price:,} VNĐ...")
        try:
            placed = await trading_client.trading.place_limit_order(
                account, symbol, OrderSide.BUY, 100, price
            )
        except Exception as exc:
            # Loi SAU khi lenh da toi san (vd het thoi gian cho) thi lenh CO THE dang treo.
            _fail_loud(
                alert_fn,
                "KHÔNG RÕ LỆNH ĐÃ LÊN SÀN CHƯA — KIỂM TRA iBoard NGAY, có lệnh treo thì HUỶ TAY",
                account, symbol, price, None, exc,
            )
        place_dict = (
            dataclasses.asdict(placed)
            if dataclasses.is_dataclass(placed)
            else getattr(placed, "__dict__", str(placed))
        )
        print(
            f"  ĐÃ ĐẶT LỆNH THÀNH CÔNG: order_id={placed.order_id}, "
            f"client_request_id={placed.client_request_id}, status={placed.status}"
        )

        # Bước 9: Huỷ ngay lệnh vừa đặt
        print(f"\nBước 9: Huỷ ngay lệnh vừa đặt (client_request_id={placed.client_request_id})...")
        cancel_dict = {}
        try:
            cancel_resp = await trading_client.trading.cancel_order(
                account, placed.client_request_id
            )
            cancel_dict = (
                dataclasses.asdict(cancel_resp)
                if dataclasses.is_dataclass(cancel_resp)
                else getattr(cancel_resp, "__dict__", str(cancel_resp))
            )
            if hasattr(cancel_resp, "status") and str(cancel_resp.status).upper() in (
                "FAILED",
                "REJECTED",
                "ERROR",
                "FAIL",
            ):
                raise RuntimeError(f"Sàn trả về trạng thái từ chối huỷ: {cancel_resp.status}")
            print(
                f"  ĐÃ HUỶ LỆNH THÀNH CÔNG: client_cancel_id={getattr(cancel_resp, 'client_cancel_id', 'N/A')}, "
                f"status={cancel_resp.status}"
            )
        except Exception as exc:
            _fail_loud(
                alert_fn,
                "HUỶ LỆNH THẤT BẠI — LỆNH THẬT CÓ THỂ ĐANG TREO — HUỶ TAY NGAY TRÊN iBoard/ứng dụng SSI",
                account, symbol, price, placed, exc,
            )

        # Bước 10: Xác nhận trạng thái THẬT sau khi huỷ. Sàn nhận yêu cầu huỷ CHƯA có nghĩa
        # lệnh đã huỷ: đọc sổ lệnh tối đa STATUS_POLL_ATTEMPTS lần và KIỂM (audit đợt 100).
        order_status_dict = None
        found = None
        portfolio = getattr(trading_client, "portfolio", None)
        if portfolio is not None:
            today = datetime.now(TZ).strftime("%Y/%m/%d")
            for attempt in range(STATUS_POLL_ATTEMPTS):
                if attempt:
                    await sleep_fn(STATUS_POLL_SLEEP_SEC)
                try:
                    today_orders = await fetch_order_history(portfolio, account, today, today)
                except Exception as e:
                    print(f"\nBước 10: lần {attempt + 1}: không đọc được sổ lệnh ({e}).")
                    continue
                for o in today_orders:
                    if o.client_request_id == placed.client_request_id or (
                        o.order_id and o.order_id == placed.order_id
                    ):
                        found = o
                        break
                if found is not None:
                    break

        exit_code = 0
        if found is None:
            print(
                "\n!! Bước 10: KHÔNG xác nhận được trạng thái lệnh qua sổ lệnh — "
                "ĐỐI CHIẾU TAY trên iBoard xem lệnh đã huỷ chưa.",
                file=sys.stderr,
            )
            exit_code = 1
        else:
            order_status_dict = (
                dataclasses.asdict(found)
                if dataclasses.is_dataclass(found)
                else getattr(found, "__dict__", str(found))
            )
            filled = int(float(found.filled_quantity or 0))
            cancelled = int(float(found.cancel_quantity or 0))
            print(
                f"\nBước 10: Trạng thái sổ lệnh: status={found.status}, "
                f"filled_qty={filled}, cancel_qty={cancelled}"
            )
            if filled > 0:
                _fail_loud(
                    alert_fn,
                    f"LỆNH ĐÃ KHỚP {filled} CỔ PHIẾU — kiểm tra iBoard; phần khớp bán được từ T+2,5",
                    account, symbol, price, placed, order_status_dict,
                )
            if cancelled < 100:
                _fail_loud(
                    alert_fn,
                    f"CHƯA XÁC NHẬN HUỶ ĐỦ 100 CỔ PHIẾU (mới huỷ {cancelled}) — HUỶ TAY NGAY TRÊN iBoard",
                    account, symbol, price, placed, order_status_dict,
                )

        # Bước 11: Lưu audit log vào JSON (không chứa token/secret)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        now_ts = datetime.now(TZ)
        log_file = LOGS_DIR / f"drill_order_{now_ts.strftime('%Y%m%d_%H%M%S')}.json"
        audit_payload = {
            "timestamp": now_ts.isoformat(),
            "account": account,
            "symbol": symbol,
            "exchange": exchange,
            "ref_price": ref,
            "floor_price": floor,
            "order_price": price,
            "quantity": 100,
            "place_order_response": place_dict,
            "cancel_order_response": cancel_dict,
            "order_status_after_cancel": order_status_dict,
        }
        log_file.write_text(
            json.dumps(audit_payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\nĐã ghi audit log diễn tập vào: {log_file}")
        return exit_code

    finally:
        if auth_created is not None:
            await auth_created.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diễn tập đặt rồi huỷ một lệnh thật (T3) — KHÔNG gửi lệnh nếu thiếu --send"
    )
    parser.add_argument(
        "--account",
        required=True,
        help="Số tài khoản giao dịch SSI (BẮT BUỘC, ví dụ: 0434221)",
    )
    parser.add_argument(
        "--symbol",
        default="VCB",
        help="Mã cổ phiếu HOSE hoặc HNX (mặc định: VCB)",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Cờ gửi lệnh thật lên sàn. Nếu không có cờ này, chỉ chạy thử (chỉ đọc).",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Đường dẫn file config (mặc định: config/config.yaml)",
    )
    args = parser.parse_args()

    # Nạp .env để tránh thiếu secret và giải quyết DNS IPv6 Windows
    try:
        from _db_common import load_dotenv, resolve_dsn
    except ImportError:
        from scripts._db_common import load_dotenv, resolve_dsn

    load_dotenv()
    if "DB_DSN" in os.environ:
        os.environ["DB_DSN"] = os.environ["DB_DSN"].replace("localhost", "127.0.0.1")

    cfg = load_config(args.config)
    dsn = resolve_dsn().replace("localhost", "127.0.0.1")
    storage = Storage(dsn)

    sys.exit(asyncio.run(
        run_drill(
            account=args.account,
            symbol=args.symbol,
            send=args.send,
            cfg=cfg,
            storage=storage,
        )
    ))


if __name__ == "__main__":
    main()
