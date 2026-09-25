from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DataSourceId(str, Enum):
    ALERTS = "alerts"
    ASSETS = "assets"
    AWS_EVENTS = "aws_events"
    IDPS_MALWARE = "idps_malware"
    LINUX_EVENTS = "linux_events"
    SCANS = "scans"
    SENSOR_MONITORING = "sensor_monitoring"
    SIGNALS = "signals"
    SYSLOG = "syslog"
    TRAFFIC = "traffic"
    USERS = "users"
    WINDOWS_EVENTS = "windows_events"


@dataclass(frozen=True)
class DataSource:
    id: DataSourceId
    label: str
    index: str
    description: str


DATA_SOURCES: dict[DataSourceId, DataSource] = {
    DataSourceId.ALERTS: DataSource(
        DataSourceId.ALERTS, "Alerts", "aella-ser-*",
        "Security events and alerts",
    ),
    DataSourceId.ASSETS: DataSource(
        DataSourceId.ASSETS, "Assets", "aella-assets-*",
        "Asset inventory and analytics data",
    ),
    DataSourceId.AWS_EVENTS: DataSource(
        DataSourceId.AWS_EVENTS, "AWS Events", "aella-cloudtrail-*",
        "AWS CloudTrail and related event data",
    ),
    DataSourceId.IDPS_MALWARE: DataSource(
        DataSourceId.IDPS_MALWARE, "IDPS / Malware Sandbox", "aella-maltrace-*",
        "IDPS, firewall threat, and malware sandbox events",
    ),
    DataSourceId.LINUX_EVENTS: DataSource(
        DataSourceId.LINUX_EVENTS, "Linux Events", "aella-audit-*",
        "Linux audit and server-sensor events",
    ),
    DataSourceId.SCANS: DataSource(
        DataSourceId.SCANS, "Scans", "aella-scan-*",
        "Vulnerability and scan data",
    ),
    DataSourceId.SENSOR_MONITORING: DataSource(
        DataSourceId.SENSOR_MONITORING, "Sensor Monitoring", "aella-ade-*",
        "Sensor statistics and monitoring data",
    ),
    DataSourceId.SIGNALS: DataSource(
        DataSourceId.SIGNALS, "Signals", "aella-signals-*",
        "Contextual signals used for threat hunting",
    ),
    DataSourceId.SYSLOG: DataSource(
        DataSourceId.SYSLOG, "Syslog", "aella-syslog-*",
        "Application and device logs from log forwarders",
    ),
    DataSourceId.TRAFFIC: DataSource(
        DataSourceId.TRAFFIC, "Traffic", "aella-adr-*",
        "Network flow and traffic metadata",
    ),
    DataSourceId.USERS: DataSource(
        DataSourceId.USERS, "Users", "aella-users-*",
        "User analytics and identity data",
    ),
    DataSourceId.WINDOWS_EVENTS: DataSource(
        DataSourceId.WINDOWS_EVENTS, "Windows Events", "aella-wineventlog-*",
        "Windows event logs and Windows server-sensor events",
    ),
}


def resolve_source(source: DataSourceId | str) -> DataSource:
    try:
        source_id = source if isinstance(source, DataSourceId) else DataSourceId(source)
        return DATA_SOURCES[source_id]
    except (ValueError, KeyError) as exc:
        raise ValueError(f"Unsupported data source: {source}") from exc


def resolve_indices(sources: list[DataSourceId]) -> str:
    if not sources:
        raise ValueError("At least one data source must be selected")
    unique = []
    seen = set()
    for source_id in sources:
        index = resolve_source(source_id).index
        if index not in seen:
            seen.add(index)
            unique.append(index)
    return ",".join(unique)


def source_labels(sources: list[DataSourceId]) -> list[str]:
    return [resolve_source(source_id).label for source_id in sources]


def source_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": item.id.value,
            "label": item.label,
            "index": item.index,
            "description": item.description,
        }
        for item in DATA_SOURCES.values()
    ]
