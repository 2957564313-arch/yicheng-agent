from __future__ import annotations

from datetime import timedelta

from app.config import BASE_DIR
from app.schemas.plan import Plan
from app.services.plan_diff import compare_plans


def test_plan_diff_reports_duration_and_shift():
    baseline = Plan.model_validate_json(
        (BASE_DIR / "fixtures" / "demo_01_saved_plan.json").read_text(
            encoding="utf-8"
        )
    )
    changed = baseline.model_copy(deep=True)
    study = next(item for item in changed.items if item.task_id == "study")
    parcel = next(item for item in changed.items if item.task_id == "parcel")
    study.end_at += timedelta(minutes=30)
    parcel.start_at += timedelta(minutes=30)
    parcel.end_at += timedelta(minutes=30)

    diff = {item.task_id: item for item in compare_plans(baseline, changed)}
    assert diff["study"].duration_delta_min == 30
    assert diff["study"].shift_min == 0
    assert diff["parcel"].shift_min == 30


def test_plan_diff_uses_hours_for_large_shifts():
    baseline = Plan.model_validate_json(
        (BASE_DIR / "fixtures" / "demo_01_saved_plan.json").read_text(
            encoding="utf-8"
        )
    )
    changed = baseline.model_copy(deep=True)
    study = next(item for item in changed.items if item.task_id == "study")
    study.start_at += timedelta(minutes=535)
    study.end_at += timedelta(minutes=535)

    change = next(
        item for item in compare_plans(baseline, changed)
        if item.task_id == "study"
    )
    assert change.summary == "顺延8小时55分钟"
