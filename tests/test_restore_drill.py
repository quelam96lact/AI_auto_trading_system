"""Unit tests cho scripts/restore_drill.py (Brief 136, sua o Brief 137).

Moi lenh goi ra ngoai di qua `runner` gia; khong can Docker.

Brief 137: so voi BAN KE SO DONG chup luc dump (`trading_<ts>.counts` canh file .dump), khong so
voi nguon dang song. Quy tac: phuc_hoi >= ban_ke, khong co bang dung sai.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.restore_drill import (
    COUNT_FAILED,
    ConfigError,
    CountsError,
    guard_target_db,
    judge_counts,
    judge_pg_restore,
    judge_tables,
    main,
    read_counts_file,
    run_drill,
)

CAGG_WARN = (
    "pg_restore: warning: there are circular foreign-key constraints on this table:\n"
    "pg_restore:   continuous_agg\n"
    "pg_restore: hint: You might not be able to restore the dump without using --disable-triggers.\n"
)


# ---------------------------------------------------------------- pg_restore
def test_pg_restore_exit_1_bao_kem_dong_loi_dau():
    a = judge_pg_restore(1, "pg_restore: error: could not read from input file: end of file\nkhac\n")
    assert len(a) == 1
    assert "could not read from input file: end of file" in a[0]


def test_pg_restore_exit_0_nhung_stderr_co_error_van_bao():
    a = judge_pg_restore(0, "pg_restore: error: could not execute query: ERROR: relation x\n")
    assert len(a) == 1 and "error" in a[0].lower()


def test_pg_restore_exit_0_voi_dung_canh_bao_continuous_agg_IM():
    assert judge_pg_restore(0, CAGG_WARN) == []


def test_pg_restore_exit_0_stderr_rong_IM():
    assert judge_pg_restore(0, "") == []


def test_pg_restore_exit_137_stderr_rong_van_bao():
    """pg_restore bi giet vi het bo nho (OOM): exit 137, stderr RONG. Truoc do moi ca hong trong test
    deu kem `error:` nen bo nhanh `rc != 0` van xanh 39/39 (Claude pha thu 30/09)."""
    a = judge_pg_restore(137, "")
    assert len(a) == 1
    assert "137" in a[0] and "CRITICAL" in a[0]


def test_pg_restore_exit_khac_0_stderr_chi_co_canh_bao_van_bao():
    assert judge_pg_restore(2, CAGG_WARN)


# ---------------------------------------------------------------- tap bang
def test_tables_khop_IM():
    assert judge_tables({"a", "b"}, {"a", "b", "extra"}) == []


def test_tables_thieu_mot_bang_bao_neu_ten():
    a = judge_tables({"bars", "orders", "engine_state"}, {"bars", "engine_state"})
    assert len(a) == 1 and "orders" in a[0]


def test_tables_nguon_rong_bao():
    assert judge_tables(set(), {"a"})


def test_tables_phuc_hoi_rong_bao():
    a = judge_tables({"a"}, set())
    assert a and "a" in a[0]


# ---------------------------------------------------------------- so dong
def test_counts_bang_ban_ke_IM():
    assert judge_counts({"bars": 936_217, "orders": 20}, {"bars": 936_217, "orders": 20}) == []


def test_counts_nhieu_hon_ban_ke_IM():
    """Co dong them sau khi chup ban ke: chi co the nhieu hon hoac bang."""
    assert judge_counts({"bars": 1000, "orders": 20}, {"bars": 1003, "orders": 20}) == []


def test_counts_it_hon_dung_1_dong_bao_neu_ten_va_hai_so():
    a = judge_counts({"bars": 936_217, "orders": 20}, {"bars": 936_217, "orders": 19})
    assert len(a) == 1
    assert "orders" in a[0] and "19" in a[0] and "20" in a[0]


def test_counts_bang_lon_it_hon_1_dong_tren_936k_van_bao():
    """Bang 99% cu de lot ~9.000 dong o bars; bay gio thieu 1 dong cung bao."""
    a = judge_counts({"bars": 936_217}, {"bars": 936_216})
    assert len(a) == 1 and "bars" in a[0]


def test_counts_bang_nho_ve_0_bao_du_bang_lon_day_du():
    a = judge_counts(
        {"bars": 936_217, "bars_daily": 2_986_214, "orders": 20},
        {"bars": 936_217, "bars_daily": 2_986_214, "orders": 0},
    )
    assert len(a) == 1 and "orders" in a[0]


def test_counts_khong_doc_duoc_o_ben_phuc_hoi_bao():
    a = judge_counts({"t": 5}, {"t": COUNT_FAILED})
    assert len(a) == 1 and "t" in a[0]


def test_counts_khong_doc_duoc_o_CA_HAI_ben_van_bao_khong_phai_khop():
    """Ca -1 == -1: hai ben cung khong do duoc KHONG phai la khop."""
    a = judge_counts({"t": COUNT_FAILED}, {"t": COUNT_FAILED})
    assert len(a) == 1 and "t" in a[0]


def test_counts_bang_rong_ca_hai_ben_IM():
    assert judge_counts({"t": 0}, {"t": 0}) == []


def test_counts_bang_khong_co_o_ben_phuc_hoi_khong_bi_dem_lan_hai_lan():
    # bang thieu do judge_tables lo; judge_counts chi xet phan giao
    assert judge_counts({"a": 1, "b": 1}, {"a": 1}) == []


# ---------------------------------------------------------------- doc ban ke
def _dump(tmp_path: Path, size=10, counts: str | None = "bars\t1000\norders\t20\n") -> Path:
    f = tmp_path / "trading_20260930_020000.dump"
    f.write_bytes(b"x" * size)
    if counts is not None:
        (tmp_path / "trading_20260930_020000.counts").write_text(counts, encoding="utf-8")
    return f


def test_read_counts_doc_dung_ten_goc_va_parse(tmp_path):
    dump = _dump(tmp_path, counts="bars\t936217\norders\t20\n\n")
    assert read_counts_file(dump) == {"bars": 936_217, "orders": 20}


def test_read_counts_khong_co_file_nem_loi_neu_ten_dump(tmp_path):
    dump = _dump(tmp_path, counts=None)
    with pytest.raises(CountsError) as e:
        read_counts_file(dump)
    assert dump.name in str(e.value)


@pytest.mark.parametrize(
    "bad",
    ["bars 1000\n", "bars\tmot\n", "bars\t-1\n", "\t5\n", "bars\t10\textra\n", "bars\t1.5\n"],
)
def test_read_counts_dong_hong_nem_loi(tmp_path, bad):
    dump = _dump(tmp_path, counts="orders\t20\n" + bad)
    with pytest.raises(CountsError):
        read_counts_file(dump)


def test_read_counts_file_rong_nem_loi(tmp_path):
    dump = _dump(tmp_path, counts="")
    with pytest.raises(CountsError):
        read_counts_file(dump)


# ---------------------------------------------------------------- chot cung
@pytest.mark.parametrize("name", ["trading", "", "  ", "TRADING", "postgres", "template1"])
def test_ten_db_dich_bi_cam(name):
    with pytest.raises(ConfigError):
        guard_target_db(name)


def test_ten_db_nhap_hop_le():
    guard_target_db("trading_restore_drill")


def test_main_ten_db_trading_thoat_2_va_khong_goi_runner(tmp_path):
    with patch("scripts.restore_drill.default_runner") as r:
        assert main(["--backup-dir", str(tmp_path), "--target-db", "trading", "--dry-run"]) == 2
    r.assert_not_called()


# ---------------------------------------------------------------- run_drill
GB = 1024**3


class FakeRunner:
    """Gia lap docker: ghi lai moi lenh, tra ket qua theo quy tac."""

    def __init__(
        self,
        restore_rc=0,
        restore_err="",
        res_tables=("bars", "orders"),
        res_counts=None,
        raise_on="",
        drop_fails=False,
        leave_db=False,
    ):
        self.calls: list[list[str]] = []
        self.restore_rc, self.restore_err = restore_rc, restore_err
        self.res_tables = res_tables
        self.res_counts = res_counts or {"bars": 1000, "orders": 20}
        self.raise_on, self.drop_fails, self.leave_db = raise_on, drop_fails, leave_db
        self.dropped = False

    def text(self) -> str:
        return "\n".join(" ".join(c) for c in self.calls)

    def queries_on(self, db: str) -> list[str]:
        out = []
        for c in self.calls:
            if "-d" in c and c[c.index("-d") + 1] == db:
                out.append(" ".join(c))
        return out

    def __call__(self, cmd: list[str]):
        self.calls.append(cmd)
        joined = " ".join(cmd)
        if self.raise_on and self.raise_on in joined:
            raise RuntimeError("boom")
        if "pg_restore" in cmd:
            return self.restore_rc, "", self.restore_err
        if "DROP DATABASE" in joined:
            if self.drop_fails:
                return 1, "", "cannot drop"
            self.dropped = True
            return 0, "", ""
        if "FROM pg_database" in joined:
            names = ["postgres", "trading"]
            if self.leave_db or not self.dropped:
                names.append("trading_restore_drill")
            return 0, "\n".join(names) + "\n", ""
        if "FROM pg_class" in joined:
            return 0, "\n".join(self.res_tables) + "\n", ""
        if "count(*)" in joined:
            for t, n in self.res_counts.items():
                if f'"{t}"' in joined:
                    return (0, f"{n}\n", "") if n != COUNT_FAILED else (1, "", "err")
            return 1, "", "no such table"
        return 0, "", ""


def _run(tmp_path, runner, free=100 * GB):
    return run_drill(
        backup_dir=tmp_path,
        target_db="trading_restore_drill",
        runner=runner,
        free_bytes=lambda: free,
    )


def test_run_drill_bang_ban_ke_IM_va_da_don_dep(tmp_path):
    _dump(tmp_path)
    r = FakeRunner()
    assert _run(tmp_path, r) == []
    assert r.dropped
    assert "CREATE EXTENSION" in r.text() and "timescaledb_pre_restore" in r.text()
    assert "timescaledb_post_restore" in r.text() and "--no-owner" in r.text()


def test_run_drill_nhieu_hon_ban_ke_IM(tmp_path):
    _dump(tmp_path)
    assert _run(tmp_path, FakeRunner(res_counts={"bars": 1002, "orders": 21})) == []


def test_run_drill_it_hon_dung_1_dong_bao_neu_ten_va_hai_so(tmp_path):
    _dump(tmp_path)
    a = _run(tmp_path, FakeRunner(res_counts={"bars": 1000, "orders": 19}))
    assert any("orders" in x and "19" in x and "20" in x for x in a)


def test_run_drill_khong_dem_dong_tren_database_trading(tmp_path):
    """Brief 137: diem tren `trading` song la loi da sua — chi con kiem `trading` van ton tai."""
    _dump(tmp_path)
    r = FakeRunner()
    _run(tmp_path, r)
    on_trading = r.queries_on("trading")
    assert on_trading == [], on_trading
    assert "count(*)" not in " ".join(c for c in r.queries_on("postgres"))


def test_run_drill_khong_co_ban_ke_bao_va_khong_cham_vao_DB(tmp_path):
    _dump(tmp_path, counts=None)
    r = FakeRunner()
    a = _run(tmp_path, r)
    assert len(a) == 1 and "CRITICAL" in a[0]
    assert "trading_20260930_020000.dump" in a[0] or "trading_20260930_020000" in a[0]
    assert "CREATE DATABASE" not in r.text()
    assert r.calls == []


def test_run_drill_ban_ke_co_dong_hong_bao_khong_bo_qua(tmp_path):
    _dump(tmp_path, counts="bars\t1000\nDONG HONG\norders\t20\n")
    r = FakeRunner()
    a = _run(tmp_path, r)
    assert len(a) == 1 and "CRITICAL" in a[0] and "DONG HONG" in a[0]
    assert r.calls == []


def test_run_drill_tap_bang_lay_tu_ban_ke_thieu_bang_bao_neu_ten(tmp_path):
    _dump(tmp_path)
    a = _run(tmp_path, FakeRunner(res_tables=("bars",)))
    assert any("orders" in x for x in a)


def test_run_drill_bang_it_hon_ban_ke_do_thieu_bang_khong_bao_kep(tmp_path):
    _dump(tmp_path)
    a = _run(tmp_path, FakeRunner(res_tables=("bars",), res_counts={"bars": 1000}))
    assert len(a) == 1 and "orders" in a[0]


def test_run_drill_thu_tu_pre_restore_truoc_pg_restore_truoc_post_restore(tmp_path):
    _dump(tmp_path)
    r = FakeRunner()
    _run(tmp_path, r)
    t = r.text()
    assert (
        t.index("CREATE EXTENSION")
        < t.index("timescaledb_pre_restore")
        < t.index("pg_restore -U")
        < t.index("timescaledb_post_restore")
    )


def test_run_drill_pg_restore_exit_1_bao_va_van_don_dep(tmp_path):
    _dump(tmp_path)
    r = FakeRunner(restore_rc=1, restore_err="pg_restore: error: could not read from input file: end of file\n")
    a = _run(tmp_path, r)
    assert any("end of file" in x for x in a)
    assert r.dropped


def test_run_drill_pg_restore_bi_giet_137_stderr_rong_bao_va_don_dep(tmp_path):
    _dump(tmp_path)
    r = FakeRunner(restore_rc=137, restore_err="")
    a = _run(tmp_path, r)
    assert any("137" in x for x in a)
    assert r.dropped


def test_run_drill_ngoai_le_o_buoc_phuc_hoi_van_DROP_DATABASE(tmp_path):
    _dump(tmp_path)
    r = FakeRunner(raise_on="pg_restore -U")
    a = _run(tmp_path, r)
    assert any("ngoại lệ" in x or "RuntimeError" in x for x in a)
    assert "DROP DATABASE" in r.text()
    assert r.dropped


def test_run_drill_lenh_don_dep_hong_thi_co_CRITICAL(tmp_path):
    _dump(tmp_path)
    a = _run(tmp_path, FakeRunner(drop_fails=True))
    assert any("dọn" in x.lower() and "CRITICAL" in x for x in a)


def test_run_drill_db_nhap_con_sot_sau_don_dep_bao(tmp_path):
    _dump(tmp_path)
    a = _run(tmp_path, FakeRunner(leave_db=True))
    assert any("trading_restore_drill" in x and "CRITICAL" in x for x in a)


def test_run_drill_khong_co_file_dump_bao_va_khong_CREATE_DATABASE(tmp_path):
    r = FakeRunner()
    a = _run(tmp_path, r)
    assert a and "CRITICAL" in a[0]
    assert "CREATE DATABASE" not in r.text()
    assert r.calls == []


def test_run_drill_dia_thieu_bao_neu_so_va_khong_CREATE_DATABASE(tmp_path):
    _dump(tmp_path, size=1000)
    r = FakeRunner()
    a = _run(tmp_path, r, free=2500)  # can 3 x 1000 = 3000
    assert a and "CRITICAL" in a[0]
    assert "3000" in a[0] or "3.000" in a[0]
    assert "CREATE DATABASE" not in r.text()


def test_run_drill_dung_ban_dump_moi_nhat_va_ban_ke_cung_ten(tmp_path):
    old = tmp_path / "trading_20260929_020000.dump"
    old.write_bytes(b"o")
    (tmp_path / "trading_20260929_020000.counts").write_text("bars\t999999\n", encoding="utf-8")
    new = _dump(tmp_path)
    os.utime(old, (1, 1))
    r = FakeRunner()
    # ban ke cu (999999) se lam bars=1000 "thieu dong" neu doc nham; doc dung ban ke moi -> IM
    assert _run(tmp_path, r) == []
    assert new.name in r.text() or str(new) in r.text()
    assert old.name not in r.text()


def test_main_dry_run_thu_muc_khong_co_dump_thoat_1_khong_gui(tmp_path):
    with patch("scripts.restore_drill.send_telegram") as s:
        assert main(["--backup-dir", str(tmp_path), "--dry-run"]) == 1
    s.assert_not_called()


def test_main_gui_hong_thoat_2(tmp_path):
    with patch("scripts.restore_drill.send_telegram", return_value=False):
        assert (
            main(["--backup-dir", str(tmp_path), "--logs-dir", str(tmp_path)]) == 2
        )


def test_main_gui_thanh_cong_thoat_1(tmp_path):
    with patch("scripts.restore_drill.send_telegram", return_value=True) as s:
        assert (
            main(["--backup-dir", str(tmp_path), "--logs-dir", str(tmp_path)]) == 1
        )
    s.assert_called_once()


def test_run_drill_bang_lon_thieu_dung_1_dong_bao(tmp_path):
    """Ca `bars`: ban ke 936.217, phuc hoi 936.216. Bang 99% cu se de lot (con ~9.000 dong)."""
    _dump(tmp_path, counts="bars\t936217\norders\t20\n")
    a = _run(tmp_path, FakeRunner(res_counts={"bars": 936_216, "orders": 20}))
    assert any("bars" in x and "936,216" in x and "936,217" in x for x in a)
