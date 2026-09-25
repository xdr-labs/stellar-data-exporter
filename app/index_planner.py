from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta

from .sources import DataSourceId, resolve_source


# Stellar Cyber 6.6 documents the concrete daily layout for Windows Events:
# aella-wineventlog-YYYY-MM-DD-*
# Other families remain on their documented wildcard until their daily naming
# is explicitly verified in Stellar Cyber documentation.
DOCUMENTED_DAILY_PREFIXES: dict[DataSourceId, str] = {
    DataSourceId.WINDOWS_EVENTS: "aella-wineventlog",
}


@dataclass(frozen=True)
class SourceIndexPlan:
    id: str
    label: str
    mode: str
    day_count: int | None
    targets: list[str]
    fallback_reason: str | None = None


@dataclass(frozen=True)
class IndexPlan:
    target: str
    sources: list[SourceIndexPlan]
    warnings: list[str]

    def as_dict(self) -> dict:
        return {
            "target": self.target,
            "sources": [asdict(item) for item in self.sources],
            "warnings": self.warnings,
        }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _covered_dates(start: datetime, end: datetime) -> list[date]:
    start_utc = _utc(start)
    end_utc = _utc(end)
    if end_utc <= start_utc:
        raise ValueError("end must be later than start")

    last_included = end_utc - timedelta(microseconds=1)
    current = start_utc.date()
    final = last_included.date()
    days: list[date] = []
    while current <= final:
        days.append(current)
        current += timedelta(days=1)
    return days


def plan_indices(
    sources: list[DataSourceId],
    *,
    start: datetime,
    end: datetime,
) -> IndexPlan:
    if not sources:
        raise ValueError("At least one data source must be selected")

    days = _covered_dates(start, end)
    planned: list[SourceIndexPlan] = []
    combined: list[str] = []
    warnings: list[str] = []
    seen: set[DataSourceId] = set()

    for source_id in sources:
        if source_id in seen:
            continue
        seen.add(source_id)
        source = resolve_source(source_id)
        prefix = DOCUMENTED_DAILY_PREFIXES.get(source_id)

        if prefix:
            targets = [f"{prefix}-{day.isoformat()}-*" for day in days]
            planned.append(
                SourceIndexPlan(
                    id=source.id.value,
                    label=source.label,
                    mode="daily",
                    day_count=len(days),
                    targets=targets,
                )
            )
            combined.extend(targets)
            continue

        reason = (
            "Daily index naming for this data-source family is not explicitly "
            "documented in the current Stellar Cyber API guidance, so the "
            "documented wildcard is retained instead of guessing."
        )
        planned.append(
            SourceIndexPlan(
                id=source.id.value,
                label=source.label,
                mode="wildcard",
                day_count=None,
                targets=[source.index],
                fallback_reason=reason,
            )
        )
        combined.append(source.index)
        warnings.append(f"{source.label}: {reason}")

    return IndexPlan(target=",".join(combined), sources=planned, warnings=warnings)
