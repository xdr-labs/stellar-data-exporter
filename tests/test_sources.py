from app.sources import DataSourceId, resolve_indices, source_catalog, source_labels


def test_resolve_indices_preserves_selection_order_and_deduplicates():
    result = resolve_indices([
        DataSourceId.WINDOWS_EVENTS,
        DataSourceId.LINUX_EVENTS,
        DataSourceId.TRAFFIC,
        DataSourceId.WINDOWS_EVENTS,
    ])
    assert result == "aella-wineventlog-*,aella-audit-*,aella-adr-*"


def test_source_catalog_exposes_friendly_labels_and_backend_mapping():
    catalog = {item["id"]: item for item in source_catalog()}

    assert catalog["windows_events"]["label"] == "Windows Events"
    assert catalog["windows_events"]["index"] == "aella-wineventlog-*"
    assert catalog["linux_events"]["label"] == "Linux Events"
    assert catalog["traffic"]["index"] == "aella-adr-*"


def test_source_labels_are_user_friendly():
    labels = source_labels([DataSourceId.ALERTS, DataSourceId.SYSLOG])
    assert labels == ["Alerts", "Syslog"]
