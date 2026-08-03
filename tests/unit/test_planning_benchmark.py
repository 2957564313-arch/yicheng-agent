from __future__ import annotations

import json

import pytest

from scripts.run_planning_benchmark import (
    ALGORITHM_DEFINITIONS,
    DEFAULT_FIXTURE,
    EXPECTED_FIXTURE_SHA256,
    RANDOM_SEED,
    load_suite,
    render_markdown,
    run_benchmark,
    write_reports,
)


@pytest.fixture(scope="module")
def benchmark_report():
    suite, digest = load_suite()
    return run_benchmark(suite, digest)


def test_frozen_fixture_has_auditable_size_seed_and_hash():
    suite, digest = load_suite()
    cases = suite["cases"]

    assert len(cases) == 24
    assert len({case["id"] for case in cases}) == len(cases)
    assert suite["random_seed"] == RANDOM_SEED
    assert digest == EXPECTED_FIXTURE_SHA256
    assert DEFAULT_FIXTURE.read_bytes()


def test_benchmark_is_deterministic():
    suite, digest = load_suite()

    first = run_benchmark(suite, digest)
    second = run_benchmark(suite, digest)

    assert first == second
    assert first["deterministic"] is True
    assert first["random_seed"] == RANDOM_SEED
    assert set(first["algorithms"]) == set(ALGORITHM_DEFINITIONS)


def test_constraint_scheduler_proves_feasibility_and_deadline_gain(
    benchmark_report,
):
    baseline = benchmark_report["algorithms"]["greedy_first_fit"]["summary"]
    constrained = benchmark_report["algorithms"][
        "constraint_scheduler_no_history"
    ]["summary"]
    complete = benchmark_report["algorithms"][
        "constraint_scheduler_min_disruption"
    ]["summary"]

    assert complete["case_count"] == 24
    assert complete["feasible_case_count"] == 24
    assert complete["feasible_completion_rate"] == 1
    assert complete["hard_constraint_violation_count"] == 0
    assert complete["deadline_satisfaction_rate"] == 1

    assert constrained["feasible_completion_rate"] == 1
    assert constrained["hard_constraint_violation_count"] == 0
    assert constrained["deadline_satisfaction_rate"] == 1

    assert (
        complete["feasible_completion_rate"]
        > baseline["feasible_completion_rate"]
    )
    assert (
        complete["hard_constraint_violation_count"]
        < baseline["hard_constraint_violation_count"]
    )
    assert (
        complete["deadline_satisfaction_rate"]
        > baseline["deadline_satisfaction_rate"]
    )


def test_minimal_disruption_ablation_reduces_plan_churn(
    benchmark_report,
):
    no_history = benchmark_report["algorithms"][
        "constraint_scheduler_no_history"
    ]["summary"]
    complete = benchmark_report["algorithms"][
        "constraint_scheduler_min_disruption"
    ]["summary"]

    assert complete["unaffected_task_count"] >= 20
    assert complete["false_move_count"] == 0
    assert complete["false_move_rate"] == 0
    assert complete["preservation_rate"] > no_history["preservation_rate"]
    assert complete["false_move_rate"] < no_history["false_move_rate"]
    assert (
        complete["total_displacement_minutes"]
        < no_history["total_displacement_minutes"]
    )


def test_report_writers_emit_json_and_markdown(
    benchmark_report,
    tmp_path,
):
    json_path = tmp_path / "planning_benchmark.json"
    markdown_path = tmp_path / "planning_benchmark.md"

    write_reports(
        benchmark_report,
        json_path=json_path,
        markdown_path=markdown_path,
    )

    assert json.loads(json_path.read_text(encoding="utf-8")) == (
        benchmark_report
    )
    markdown = markdown_path.read_text(encoding="utf-8")
    assert markdown == render_markdown(benchmark_report)
    assert "可行完成率" in markdown
    assert EXPECTED_FIXTURE_SHA256 in markdown
    assert "不是用户研究" in markdown
