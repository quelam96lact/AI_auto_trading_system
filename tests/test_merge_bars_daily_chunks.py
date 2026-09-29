from datetime import UTC, datetime

from scripts.merge_bars_daily_chunks import get_db_name, group_chunks_by_year


def test_get_db_name():
    assert get_db_name("postgresql://user:pass@127.0.0.1:5432/trading") == "trading"
    assert get_db_name("postgresql://user:pass@127.0.0.1:5432/rehearsal128") == "rehearsal128"
    assert get_db_name("postgresql://user:pass@localhost:5432/trading_test") == "trading_test"
    assert get_db_name("dbname=trading user=trading") == "trading"


def test_group_chunks_by_year():
    sample_chunks = [
        {
            "chunk_schema": "_timescaledb_internal",
            "chunk_name": "_hyper_1_1_chunk",
            "range_start": datetime(2015, 12, 31, tzinfo=UTC),
            "range_end": datetime(2016, 1, 7, tzinfo=UTC),
            "regclass": "_timescaledb_internal._hyper_1_1_chunk",
        },
        {
            "chunk_schema": "_timescaledb_internal",
            "chunk_name": "_hyper_1_2_chunk",
            "range_start": datetime(2016, 1, 7, tzinfo=UTC),
            "range_end": datetime(2016, 1, 14, tzinfo=UTC),
            "regclass": "_timescaledb_internal._hyper_1_2_chunk",
        },
        {
            "chunk_schema": "_timescaledb_internal",
            "chunk_name": "_hyper_1_3_chunk",
            "range_start": datetime(2016, 1, 14, tzinfo=UTC),
            "range_end": datetime(2016, 1, 21, tzinfo=UTC),
            "regclass": "_timescaledb_internal._hyper_1_3_chunk",
        },
        {
            "chunk_schema": "_timescaledb_internal",
            "chunk_name": "_hyper_1_4_chunk",
            "range_start": datetime(2017, 1, 5, tzinfo=UTC),
            "range_end": datetime(2017, 1, 12, tzinfo=UTC),
            "regclass": "_timescaledb_internal._hyper_1_4_chunk",
        },
    ]

    groups = group_chunks_by_year(sample_chunks)
    assert list(groups.keys()) == [2015, 2016, 2017]
    assert len(groups[2015]) == 1
    assert len(groups[2016]) == 2
    assert len(groups[2017]) == 1
