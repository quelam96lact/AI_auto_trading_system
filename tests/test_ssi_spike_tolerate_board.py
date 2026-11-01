"""SSI tra board='DERIVATIVES' (01/11/2026) lam SecuritiesInfo.from_list cua ssi_sdk
nem ValueError. scripts/_ssi_spike_common.tolerate_unknown_board va lai."""

import pytest
from ssi_sdk.enums import Board
from ssi_sdk.models.market_data import SecuritiesInfo

from scripts._ssi_spike_common import tolerate_unknown_board

ROWS = [
    {"symbol": "VCB", "board": "HOSE", "listedShare": 10},
    {"symbol": "41I1G2000", "board": "DERIVATIVES"},
    {"symbol": "XYZ"},
]


@pytest.fixture
def restore_from_list(monkeypatch):
    # monkeypatch tra lai from_list goc sau test, khong de va ro sang test khac
    monkeypatch.setattr(SecuritiesInfo, "from_list", SecuritiesInfo.from_list)


def test_sdk_goc_van_chet_voi_board_la(restore_from_list):
    with pytest.raises(ValueError):
        SecuritiesInfo.from_list(ROWS)


def test_va_giu_board_hop_le_va_bo_board_la(restore_from_list):
    tolerate_unknown_board()
    out = SecuritiesInfo.from_list(ROWS)
    assert [r.symbol for r in out] == ["VCB", "41I1G2000", "XYZ"]
    assert out[0].board == Board.HOSE
    assert out[0].listed_shares == 10
    assert out[1].board is None
    assert out[2].board is None


def test_goi_nhieu_lan_chi_va_mot_lan(restore_from_list):
    tolerate_unknown_board()
    first = SecuritiesInfo.from_list
    tolerate_unknown_board()
    assert SecuritiesInfo.from_list == first
