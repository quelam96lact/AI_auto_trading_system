"""Unit tests cho scripts/restore_drill.py (Brief 136).

Moi lenh goi ra ngoai di qua `runner` gia; khong can Docker.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.restore_drill import (
    COUNT_FAILED,
    ConfigError,
    guard_target_db,
    judge_counts,
    judge_pg_restore,
    judge_tables,
    main,
    run_drill,
)

CAGG_WARN = (
    "pg_restore: warning: there are circular foreign-key constraints on this table:\n"
    "pg_restore:   continuous_agg\n"
    "pg_restore: hint: You might not be able to restore the dump without using --disable-triggers.\n"
)


# ---------------------------------------------------------------- pg_restore
def test_pg_restore_exit_1_bao_kem_dong_loi_dau():
    a = judge_pg_restore(
        1, "pg_restore: error: could not read from input file: end of file\nkhac\n"
    )
    assert len(a) == 1
    assert "could not read from input file: end of file" in a[0]


def test_pg_restore_exit_0_nhung_stderr_co_error_van_bao():
    a = judge_pg_restore(
        0, "pg_restore: error: could not execute query: ERROR: relation x\n"
    )
    assert len(a) == 1 and "error" in a[0].lower()


def test_pg_restore_exit_0_voi_dung_canh_bao_continuous_agg_IM():
    assert judge_pg_restore(0, CAGG_WARN) == []


def test_pg_restore_exit_0_stderr_rong_IM():
    assert judge_pg_restore(0, "") == []


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
def test_counts_khop_IM():
    assert (
        judge_counts({"bars": 936_217, "orders": 20}, {"bars": 936_217, "orders": 20})
        == []
    )


def test_counts_mot_bang_con_90_phan_tram_bao_neu_ten_va_hai_so():
    a = judge_counts({"bars": 1000, "orders": 100}, {"bars": 1000, "orders": 90})
    assert len(a) == 1
    assert "orders" in a[0] and "90" in a[0] and "100" in a[0]


def test_counts_bang_nho_ve_0_bao_du_bang_lon_con_99_99():
    """Ca that do 30/09: bars 936.083/936.217 (99,99%) nhung orders = 0."""
    a = judge_counts(
        {"bars": 936_217, "bars_daily": 2_986_214, "orders": 20},
        {"bars": 936_083, "bars_daily": 2_986_214, "orders": 0},
    )
    assert len(a) == 1 and "orders" in a[0]


def test_counts_lech_0_01_phan_tram_IM():
    assert judge_counts({"bars": 936_217}, {"bars": 936_083}) == []


def test_counts_khong_doc_duoc_o_ben_nguon_bao():
    a = judge_counts({"t": COUNT_FAILED}, {"t": 5})
    assert len(a) == 1 and "t" in a[0]


def test_counts_khong_doc_duoc_o_ben_phuc_hoi_bao():
    a = judge_counts({"t": 5}, {"t": COUNT_FAILED})
    assert len(a) == 1


def test_counts_khong_doc_duoc_o_CA_HAI_ben_van_bao_khong_phai_khop():
    """Ca -1 == -1: hai ben cung khong do duoc KHONG phai la khop."""
    a = judge_counts({"t": COUNT_FAILED}, {"t": COUNT_FAILED})
    assert len(a) == 1 and "t" in a[0]


def test_counts_bang_rong_ca_hai_ben_IM():
    assert judge_counts({"t": 0}, {"t": 0}) == []


def test_counts_bang_khong_co_o_ben_phuc_hoi_khong_bi_dem_lan_hai_lan():
    # bang thieu do judge_tables lo; judge_counts chi xet phan giao
    assert judge_counts({"a": 1, "b": 1}, {"a": 1}) == []


# ---------------------------------------------------------------- chot cung
@pytest.mark.parametrize(
    "name", ["trading", "", "  ", "TRADING", "postgres", "template1"]
)
def test_ten_db_dich_bi_cam(name):
    with pytest.raises(ConfigError):
        guard_target_db(name)


def test_ten_db_nhap_hop_le():
    guard_target_db("trading_restore_drill")


def test_main_ten_db_trading_thoat_2_va_khong_goi_runner(tmp_path):
    with patch("scripts.restore_drill.default_runner") as r:
        assert (
            main(["--backup-dir", str(tmp_path), "--target-db", "trading", "--dry-run"])
            == 2
        )
    r.assert_not_called()


# ---------------------------------------------------------------- run_drill
GB = 1024**3


class FakeRunner:
    """Gia lap docker: ghi lai moi lenh, tra ket qua theo quy tac."""

    def __init__(
        self,
        restore_rc=0,
        restore_err="",
        src_tables=("bars", "orders"),
        res_tables=("bars", "orders"),
        src_counts=None,
        res_counts=None,
        raise_on="",
        drop_fails=False,
        leave_db=False,
    ):
        self.calls: list[list[str]] = []
        self.restore_rc, self.restore_err = restore_rc, restore_err
        self.src_tables, self.res_tables = src_tables, res_tables
        self.src_counts = src_counts or {"bars": 1000, "orders": 20}
        self.res_counts = res_counts or {"bars": 1000, "orders": 20}
        self.raise_on, self.drop_fails, self.leave_db = raise_on, drop_fails, leave_db
        self.dropped = False

    def text(self) -> str:
        return "\n".join(" ".join(c) for c in self.calls)

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
            names = ["postgres", "trading"] + (
                [] if self.dropped and not self.leave_db else ["trading_restore_drill"]
            )
            if self.leave_db:
                names.append("trading_restore_drill")
            return 0, "\n".join(names) + "\n", ""
        if "FROM pg_class" in joined:
            db = cmd[cmd.index("-d") + 1]
            tables = self.src_tables if db == "trading" else self.res_tables
            return 0, "\n".join(tables) + "\n", ""
        if "count(*)" in joined:
            db = cmd[cmd.index("-d") + 1]
            counts = self.src_counts if db == "trading" else self.res_counts
            for t, n in counts.items():
                if f'"{t}"' in joined:
                    return (0, f"{n}\n", "") if n != COUNT_FAILED else (1, "", "err")
            return 1, "", "no such table"
        return 0, "", ""


def _dump(tmp_path: Path, size=10) -> Path:
    f = tmp_path / "trading_20260930_020000.dump"
    f.write_bytes(b"x" * size)
    return f


def _run(tmp_path, runner, free=100 * GB, **kw):
    return run_drill(
        backup_dir=tmp_path,
        target_db="trading_restore_drill",
        runner=runner,
        free_bytes=lambda: free,
        **kw,
    )


def test_run_drill_moi_thu_khop_IM_va_da_don_dep(tmp_path):
    _dump(tmp_path)
    r = FakeRunner()
    assert _run(tmp_path, r) == []
    assert r.dropped
    assert "CREATE EXTENSION" in r.text() and "timescaledb_pre_restore" in r.text()
    assert "timescaledb_post_restore" in r.text() and "--no-owner" in r.text()


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
    r = FakeRunner(
        restore_rc=1,
        restore_err="pg_restore: error: could not read from input file: end of file\n",
    )
    a = _run(tmp_path, r)
    assert any("end of file" in x for x in a)
    assert r.dropped


def test_run_drill_thieu_bang_bao_neu_ten(tmp_path):
    _dump(tmp_path)
    a = _run(tmp_path, FakeRunner(res_tables=("bars",)))
    assert any("orders" in x for x in a)


def test_run_drill_bang_con_90_phan_tram_bao(tmp_path):
    _dump(tmp_path)
    a = _run(tmp_path, FakeRunner(res_counts={"bars": 1000, "orders": 18}))
    assert any("orders" in x and "18" in x and "20" in x for x in a)


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


def test_run_drill_dung_ban_dump_moi_nhat(tmp_path):
    old = tmp_path / "trading_20260929_020000.dump"
    old.write_bytes(b"o")
    new = _dump(tmp_path)
    import os

    os.utime(old, (1, 1))
    r = FakeRunner()
    _run(tmp_path, r)
    assert new.name in r.text() or str(new) in r.text()
    assert old.name not in r.text()


def test_main_dry_run_thu_muc_khong_co_dump_thoat_1_khong_gui(tmp_path):
    with patch("scripts.restore_drill.send_telegram") as s:
        assert main(["--backup-dir", str(tmp_path), "--dry-run"]) == 1
    s.assert_not_called()


def test_main_gui_hong_thoat_2(tmp_path):
    with patch("scripts.restore_drill.send_telegram", return_value=False):
        assert main(["--backup-dir", str(tmp_path)]) == 2


def test_main_gui_thanh_cong_thoat_1(tmp_path):
    with patch("scripts.restore_drill.send_telegram", return_value=True) as s:
        assert main(["--backup-dir", str(tmp_path)]) == 1
    s.assert_called_once()
