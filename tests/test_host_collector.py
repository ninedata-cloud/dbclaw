from datetime import datetime, timedelta, timezone

from backend.services.host_collector import _calculate_disk_io_rates


def test_calculate_disk_io_rates_with_utc_naive_timestamp():
    current_metrics = {
        "disk_reads_total": 1180,
        "disk_writes_total": 920,
        "disk_read_sectors_total": 23600,
        "disk_write_sectors_total": 18400,
    }
    last_data = {
        "disk_reads_total": 1000,
        "disk_writes_total": 800,
        "disk_read_sectors_total": 20000,
        "disk_write_sectors_total": 16000,
    }
    current_time = datetime(2026, 4, 21, 10, 0, 0)
    last_collected_at = current_time - timedelta(seconds=60)

    _calculate_disk_io_rates(
        current_metrics,
        last_data,
        last_collected_at,
        current_time=current_time,
    )

    assert current_metrics["disk_read_iops"] == 3.0
    assert current_metrics["disk_write_iops"] == 2.0
    assert current_metrics["disk_read_kb_per_sec"] == 30.0
    assert current_metrics["disk_write_kb_per_sec"] == 20.0


def test_calculate_disk_io_rates_handles_future_naive_timestamp_from_local_timezone():
    current_metrics = {
        "disk_reads_total": 1120,
        "disk_writes_total": 860,
        "disk_read_sectors_total": 22400,
        "disk_write_sectors_total": 17200,
    }
    last_data = {
        "disk_reads_total": 1000,
        "disk_writes_total": 800,
        "disk_read_sectors_total": 20000,
        "disk_write_sectors_total": 16000,
    }
    current_time = datetime(2026, 4, 21, 10, 0, 0)
    # 模拟 PostgreSQL 以 UTC+8 本地时间写入 naive timestamp，实际 UTC 时间应为 09:59:00
    last_collected_at = datetime(2026, 4, 21, 17, 59, 0)

    _calculate_disk_io_rates(
        current_metrics,
        last_data,
        last_collected_at,
        current_time=current_time,
        local_tz=timezone(timedelta(hours=8)),
    )

    assert current_metrics["disk_read_iops"] == 2.0
    assert current_metrics["disk_write_iops"] == 1.0
    assert current_metrics["disk_read_kb_per_sec"] == 20.0
    assert current_metrics["disk_write_kb_per_sec"] == 10.0
