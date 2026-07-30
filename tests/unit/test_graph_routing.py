from app.graph import route_after_validate


def test_validation_error_does_not_trigger_blind_deterministic_retry():
    state = {
        "validation_issues": [
            {
                "code": "task_unscheduled",
                "severity": "error",
                "message": "No feasible interval remains.",
            }
        ],
        "replan_count": 0,
        "max_replans": 2,
    }

    assert route_after_validate(state) == "respond"


def test_valid_plan_routes_to_response():
    assert route_after_validate({"validation_issues": []}) == "respond"
