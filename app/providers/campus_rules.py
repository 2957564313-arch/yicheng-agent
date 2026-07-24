from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from app.schemas.common import DataSource
from app.schemas.context import CongestionWindow, RetrievedFact


WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class CampusRulesRepository:
    def __init__(
        self,
        opening_hours_path: Path,
        campus_rules_path: Path,
        class_periods_path: Path,
        timezone_name: str,
    ) -> None:
        self.timezone = ZoneInfo(timezone_name)
        opening_payload = json.loads(
            opening_hours_path.read_text(encoding="utf-8")
        )
        self.data_quality = opening_payload.get("data_quality", "unknown")
        self._opening_rules = {
            rule["location_id"]: rule
            for rule in opening_payload.get("rules", [])
        }
        rules_payload = json.loads(
            campus_rules_path.read_text(encoding="utf-8")
        )
        self._rules = rules_payload.get("rules", [])
        class_payload = json.loads(
            class_periods_path.read_text(encoding="utf-8")
        )
        self._congestion_windows = class_payload.get(
            "congestion_windows",
            [],
        )

    def opening_windows(
        self,
        location_id: str,
        target_date: date,
    ) -> list[tuple[datetime, datetime]]:
        rule = self._opening_rules.get(location_id)
        if not rule:
            return []
        effective_from = date.fromisoformat(rule["effective_from"])
        effective_to = (
            date.fromisoformat(rule["effective_to"])
            if rule.get("effective_to")
            else None
        )
        if target_date < effective_from:
            return []
        if effective_to and target_date > effective_to:
            return []

        key = WEEKDAY_KEYS[target_date.weekday()]
        raw_windows = rule.get("weekly", {}).get(key, [])
        return [
            (
                datetime.combine(
                    target_date,
                    time.fromisoformat(start),
                    self.timezone,
                ),
                datetime.combine(
                    target_date,
                    time.fromisoformat(end),
                    self.timezone,
                ),
            )
            for start, end in raw_windows
        ]

    def facts_for_locations(
        self,
        location_ids: set[str],
    ) -> list[RetrievedFact]:
        facts = []
        for rule in self._rules:
            applies_to = set(rule.get("applies_to", []))
            if not (applies_to & location_ids):
                continue
            verified_at = (
                date.fromisoformat(rule["verified_at"])
                if rule.get("verified_at")
                else None
            )
            facts.append(
                RetrievedFact(
                    id=rule["id"],
                    content=rule["content"],
                    applies_to=list(applies_to),
                    priority=rule.get("priority", 0),
                    source=DataSource.STRUCTURED,
                    source_ref=rule.get("source_url"),
                    verified_at=verified_at,
                )
            )
        return facts

    def congestion_windows(
        self,
        target_date: date,
    ) -> list[tuple[datetime, datetime]]:
        return [
            (item.start_at, item.end_at)
            for item in self.congestion_contexts(target_date)
        ]

    def congestion_contexts(
        self,
        target_date: date,
    ) -> list[CongestionWindow]:
        result: list[CongestionWindow] = []
        for raw in self._congestion_windows:
            try:
                result.append(
                    CongestionWindow(
                        start_at=datetime.combine(
                            target_date,
                            time.fromisoformat(raw["start"]),
                            self.timezone,
                        ),
                        end_at=datetime.combine(
                            target_date,
                            time.fromisoformat(raw["end"]),
                            self.timezone,
                        ),
                        duration_multiplier=float(
                            raw.get("duration_multiplier", 1.25)
                        ),
                        minimum_extra_min=int(
                            raw.get("minimum_extra_min", 3)
                        ),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return result
