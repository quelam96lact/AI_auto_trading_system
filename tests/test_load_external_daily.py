"""Unit tests for external daily data loader pure functions (Brief 115).

Tests:
1. parse_frb_h10_xml: extracts valid dates and prices, skips 'ND', respects max_date.
2. parse_ecb_csv: extracts dates and prices from ECB CSV format, respects max_date.
3. calculate_data_summary: verifies row count, date span, nonpositive count, duplicates, and max business day gap.
"""

from __future__ import annotations

from datetime import date

from scripts.load_external_daily import (
    calculate_data_summary,
    parse_ecb_csv,
    parse_frb_h10_xml,
)

SAMPLE_FRB_XML = """<?xml version="1.0" encoding="UTF-8"?>
<message:MessageGroup xmlns:message="http://www.SDMX.org/resources/SDMXML/schemas/v1_0/message"
                      xmlns:common="http://www.SDMX.org/resources/SDMXML/schemas/v1_0/common"
                      xmlns:frb="http://www.federalreserve.gov/structure/compact/common"
                      xmlns:kf="http://www.federalreserve.gov/structure/compact/H10_H10">
  <frb:DataSet id="H10">
    <kf:Series CURRENCY="EUR" FREQ="9" FX="BRD" SERIES_NAME="RXI$US_N.B.EU">
      <frb:Obs OBS_STATUS="A" OBS_VALUE="1.1812" TIME_PERIOD="1999-01-04"/>
      <frb:Obs OBS_STATUS="A" OBS_VALUE="1.1760" TIME_PERIOD="1999-01-05"/>
      <frb:Obs OBS_STATUS="A" OBS_VALUE="ND" TIME_PERIOD="1999-01-06"/>
      <frb:Obs OBS_STATUS="A" OBS_VALUE="1.1630" TIME_PERIOD="2026-08-31"/>
      <frb:Obs OBS_STATUS="A" OBS_VALUE="1.1550" TIME_PERIOD="2026-09-02"/>
    </kf:Series>
    <kf:Series CURRENCY="JPY" FREQ="9" FX="BRD" SERIES_NAME="RXI_N.B.JA">
      <frb:Obs OBS_STATUS="A" OBS_VALUE="150.25" TIME_PERIOD="2026-08-29"/>
      <frb:Obs OBS_STATUS="A" OBS_VALUE="150.50" TIME_PERIOD="2026-08-31"/>
    </kf:Series>
  </frb:DataSet>
</message:MessageGroup>
"""

SAMPLE_ECB_CSV = """KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE,OBS_STATUS
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-08-27,1.1654,A
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-08-28,1.1598,A
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-08-31,1.1617,A
EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-09-01,1.1620,A
"""


def test_parse_frb_h10_xml():
    """Verify FRB XML parsing extracts valid records, skips 'ND', and respects max_date."""
    records = parse_frb_h10_xml(
        xml_content=SAMPLE_FRB_XML,
        series_name="RXI$US_N.B.EU",
        symbol="EURUSD",
        max_date=date(2026, 8, 31),
    )
    assert len(records) == 3
    # Check first record
    assert records[0]["date"] == date(1999, 1, 4)
    assert records[0]["close"] == 1.1812
    assert records[0]["source"] == "FRB_H10"
    assert records[0]["symbol"] == "EURUSD"
    # Check second record (1999-01-05)
    assert records[1]["date"] == date(1999, 1, 5)
    assert records[1]["close"] == 1.1760
    # 1999-01-06 was 'ND' -> skipped
    # 2026-08-31 is present
    assert records[2]["date"] == date(2026, 8, 31)
    assert records[2]["close"] == 1.1630
    # 2026-09-02 must be sealed (filtered out by max_date)
    assert not any(r["date"] > date(2026, 8, 31) for r in records)


def test_parse_ecb_csv():
    """Verify ECB CSV parsing extracts records and filters out dates after max_date."""
    records = parse_ecb_csv(
        csv_content=SAMPLE_ECB_CSV,
        symbol="EURUSD",
        max_date=date(2026, 8, 31),
    )
    assert len(records) == 3
    assert records[0]["date"] == date(2026, 8, 27)
    assert records[0]["close"] == 1.1654
    assert records[0]["source"] == "ECB"
    assert records[1]["date"] == date(2026, 8, 28)
    assert records[2]["date"] == date(2026, 8, 31)
    assert records[2]["close"] == 1.1617
    # 2026-09-01 is filtered out
    assert not any(r["date"] > date(2026, 8, 31) for r in records)


def test_calculate_data_summary():
    """Verify summary calculations: row count, date span, invalid prices, duplicates, business day gaps."""
    # Create sample records with a known holiday / business day gap
    # Friday 2026-08-21 to Monday 2026-08-24 -> 1 business day gap (normal weekend)
    # Monday 2026-08-24 to Friday 2026-08-28 -> gap of 4 business days!
    records = [
        {"date": date(2026, 8, 21), "close": 100.0},
        {"date": date(2026, 8, 24), "close": 101.0},
        {"date": date(2026, 8, 24), "close": 101.0},  # duplicate
        {"date": date(2026, 8, 28), "close": -1.0},   # nonpositive
    ]

    summary = calculate_data_summary(records)
    assert summary["total_rows"] == 4
    assert summary["first_date"] == date(2026, 8, 21)
    assert summary["last_date"] == date(2026, 8, 28)
    assert summary["nonpositive_count"] == 1
    assert summary["duplicate_dates_count"] == 1
    # Between 2026-08-24 (Mon) and 2026-08-28 (Fri):
    # Missing Tue, Wed, Thu = 3 missing business days, delta = 4 business days
    assert summary["max_business_day_gap"] == 4
