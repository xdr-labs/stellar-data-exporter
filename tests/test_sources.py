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


from datetime import UTC, datetime

from app.index_planner import plan_indices


def test_index_planner_scopes_documented_windows_family_to_covered_utc_days():
    plan = plan_indices(
        [DataSourceId.WINDOWS_EVENTS],
        start=datetime(2026, 9, 23, tzinfo=UTC),
        end=datetime(2026, 9, 26, tzinfo=UTC),
    )
    assert plan.target == (
        "aella-wineventlog-2026-09-23-*,"
        "aella-wineventlog-2026-09-24-*,"
        "aella-wineventlog-2026-09-25-*"
    )
    assert plan.sources[0].mode == "daily"
    assert plan.sources[0].day_count == 3
    assert plan.warnings == []


def test_index_planner_uses_safe_wildcard_fallback_for_unverified_families():
    plan = plan_indices(
        [DataSourceId.LINUX_EVENTS, DataSourceId.TRAFFIC],
        start=datetime(2026, 9, 23, tzinfo=UTC),
        end=datetime(2026, 9, 26, tzinfo=UTC),
    )
    assert plan.target == "aella-audit-*,aella-adr-*"
    assert [item.mode for item in plan.sources] == ["wildcard", "wildcard"]
    assert len(plan.warnings) == 2


def test_index_planner_end_is_exclusive_at_midnight():
    plan = plan_indices(
        [DataSourceId.WINDOWS_EVENTS],
        start=datetime(2026, 9, 23, 12, tzinfo=UTC),
        end=datetime(2026, 9, 25, tzinfo=UTC),
    )
    assert plan.sources[0].targets == [
        "aella-wineventlog-2026-09-23-*",
        "aella-wineventlog-2026-09-24-*",
    ]
