from __future__ import annotations

import json

from app.config import BASE_DIR


def chat_case(
    case_id: str,
    category: str,
    query: str,
    *,
    min_task_count: int,
    expected_status: str = "completed",
    warning_codes: list[str] | None = None,
    plan_status: str | None = "auto",
    now: str = "2026-07-23T08:00:00+08:00",
    answer_contains: list[str] | None = None,
    answer_not_contains: list[str] | None = None,
    min_answer_length: int = 0,
    required_task_titles: list[str] | None = None,
    forbidden_task_titles: list[str] | None = None,
    required_travel_mode: str | None = None,
    min_congestion_delay_min: int = 0,
    target_date: str | None = None,
) -> dict:
    resolved_plan_status = (
        ("valid" if expected_status == "completed" else None)
        if plan_status == "auto"
        else plan_status
    )
    return {
        "case_id": case_id,
        "category": category,
        "endpoint": "chat",
        "request": {
            "user_id": "evaluation_user",
            "thread_id": f"thread_{case_id}",
            "query": query,
            "mode": "offline",
            "client_context": {
                "now": now
            }
        },
        "expected": {
            "http_status": 200,
            "status": expected_status,
            "plan_status": resolved_plan_status,
            "min_task_count": min_task_count,
            "warning_codes": (
                ["API_DEGRADED"]
                if warning_codes is None
                else warning_codes
            ),
            "answer_contains": answer_contains or [],
            "answer_not_contains": answer_not_contains or [],
            "min_answer_length": min_answer_length,
            "required_task_titles": required_task_titles or [],
            "forbidden_task_titles": forbidden_task_titles or [],
            "required_travel_mode": required_travel_mode,
            "min_congestion_delay_min": min_congestion_delay_min,
            "target_date": target_date,
        }
    }

def build_cases() -> list[dict]:
    base_queries = [
        ("明天下午安排两个小时自习。", 1),
        ("明天去图书馆学习一个小时。", 1),
        ("明天下午取快递，快递站18点关门。", 1),
        ("明天安排吃晚饭。", 1),
        ("明天晚上去跑步。", 1),
        ("明天下午自习两个小时，然后取快递，18点前完成。", 2),
        ("明天取快递后吃晚饭，快递站18点关门。", 2),
        ("明天吃晚饭以后跑步。", 2),
        ("明天下午学习两个小时，晚上运动。", 2),
        ("明天下午自习两个小时、取快递、吃饭和跑步。", 4),
    ]
    cases = []
    for round_index in range(3):
        for index, (query, count) in enumerate(base_queries, start=1):
            cases.append(
                chat_case(
                    f"normal_{round_index + 1}_{index:02d}",
                    "normal",
                    query,
                    min_task_count=count,
                )
            )

    for index, hour in enumerate((16, 17, 18, 18, 17, 16, 18, 17, 18, 16), 1):
        cases.append(
            chat_case(
                f"deadline_{index:02d}",
                "deadline",
                f"明天下午取快递，快递站{hour}点关门。",
                min_task_count=1,
            )
        )

    degraded_queries = [
        "明天下午去图书馆自习两个小时，再去快递站，结合天气安排。",
        "明天下午学习一个小时并取快递。",
        "明天晚上吃饭后跑步，结合天气安排。",
        "明天下午自习两个小时，晚上跑步。",
        "明天取快递以后吃饭。",
    ]
    for index in range(10):
        query = degraded_queries[index % len(degraded_queries)]
        count = sum(
            [
                ("自习" in query or "学习" in query),
                ("快递" in query),
                ("吃饭" in query),
                ("跑步" in query),
            ]
        )
        cases.append(
            chat_case(
                f"degraded_{index + 1:02d}",
                "degraded",
                query,
                min_task_count=count,
                warning_codes=["API_DEGRADED"],
            )
        )

    broad_scenario_cases = [
        chat_case(
            "broad_academic_combo",
            "broad_student_scenarios",
            (
                "明天下午2点后在图书馆复习高数2小时，然后写作业90分钟，"
                "晚上7点前全部完成。"
            ),
            min_task_count=2,
            required_task_titles=["复习", "作业"],
        ),
        chat_case(
            "broad_project_lab",
            "broad_student_scenarios",
            "明天下午2点后在实验室写代码2小时，晚上6点前完成。",
            min_task_count=1,
            required_task_titles=["项目"],
        ),
        chat_case(
            "broad_fixed_meeting",
            "broad_student_scenarios",
            "明天下午3点到4点开组会，然后在图书馆复习1小时。",
            min_task_count=2,
            required_task_titles=["组会", "复习"],
        ),
        chat_case(
            "broad_life_activity_sequence",
            "broad_student_scenarios",
            (
                "明天中午吃午饭45分钟，然后回宿舍洗衣服30分钟，"
                "最后参加社团活动1小时。"
            ),
            min_task_count=3,
            required_task_titles=["午饭", "洗衣", "社团"],
        ),
        chat_case(
            "broad_three_meals",
            "broad_student_scenarios",
            "明天吃早餐30分钟，中午吃午饭45分钟，晚上吃晚饭45分钟。",
            min_task_count=3,
            required_task_titles=["早餐", "午饭", "晚饭"],
        ),
        chat_case(
            "broad_rest_and_call",
            "broad_student_scenarios",
            (
                "明天下午写作业2小时，然后回宿舍休息30分钟，"
                "再打电话20分钟。"
            ),
            min_task_count=3,
            required_task_titles=["作业", "休息", "电话"],
        ),
        chat_case(
            "broad_scoped_admin_deadline",
            "broad_student_scenarios",
            (
                "明天下午复习2小时，18点前提交材料30分钟，"
                "晚上参加社团活动1小时。"
            ),
            min_task_count=3,
            required_task_titles=["复习", "校园事务", "社团"],
        ),
        chat_case(
            "broad_location_scoping",
            "broad_student_scenarios",
            "明天下午在实验室写代码2小时，再回宿舍休息30分钟。",
            min_task_count=2,
            required_task_titles=["项目", "休息"],
        ),
        chat_case(
            "broad_shopping_laundry",
            "broad_student_scenarios",
            "明天下午去超市买日用品45分钟，再回宿舍洗衣服30分钟。",
            min_task_count=2,
            required_task_titles=["采购", "洗衣"],
        ),
        chat_case(
            "broad_exam_review",
            "broad_student_scenarios",
            "明天9点到11点考试，下午在图书馆复习2小时。",
            min_task_count=2,
            required_task_titles=["考试", "复习"],
        ),
        chat_case(
            "broad_collaboration_report",
            "broad_student_scenarios",
            (
                "明天下午小组讨论1小时，然后写实验报告2小时，"
                "18点前全部完成。"
            ),
            min_task_count=2,
            required_task_titles=["会议", "作业"],
        ),
        chat_case(
            "broad_morning_admin",
            "broad_student_scenarios",
            "明天上午打印资料30分钟，再去图书馆预习1小时。",
            min_task_count=2,
            required_task_titles=["校园事务", "复习"],
        ),
    ]
    cases.extend(broad_scenario_cases)

    for index in range(5):
        cases.append(
            chat_case(
                f"clarification_{index + 1:02d}",
                "clarification",
                "请帮我安排一下。",
                min_task_count=0,
                expected_status="needs_clarification",
                warning_codes=[],
            )
        )

    for index, demo_id in enumerate(
        [
            "demo_01_normal",
            "demo_02_emergency",
            "demo_03_degraded",
            "demo_01_normal",
            "demo_02_emergency",
        ],
        start=1,
    ):
        cases.append(
            {
                "case_id": f"demo_{index:02d}",
                "category": "demo",
                "endpoint": "demo",
                "demo_id": demo_id,
                "expected": {
                    "http_status": 200,
                    "status": "completed",
                    "plan_status": "valid",
                    "min_task_count": 2,
                    "warning_codes": ["API_DEGRADED"],
                },
            }
        )

    hdu_constraint_cases = [
        (
            "complex_course_courier_run",
            (
                "7月24日第3到4节有课，下课后去图书馆七楼自习2小时，"
                "18点前取顺丰，晚上去西北田径场完成40分钟阳光长跑。"
            ),
            4,
            "completed",
            ["API_DEGRADED", "ROUTE_FALLBACK"],
        ),
        (
            "clinic_and_hot_water",
            "7月24日下午去校医院就诊30分钟，晚上回宿舍洗澡30分钟。",
            2,
            "completed",
            ["API_DEGRADED", "ROUTE_FALLBACK"],
        ),
        (
            "weekend_badminton_closed",
            (
                "7月25日下午去校医院就诊30分钟，再打羽毛球1小时，"
                "晚上回宿舍洗澡30分钟。"
            ),
            2,
            "partial",
            ["OUTSIDE_OPENING_HOURS", "TASK_UNSCHEDULED"],
        ),
        (
            "library_floor_closing",
            "7月24日21点后去图书馆七楼自习1小时。",
            0,
            "partial",
            ["TASK_UNSCHEDULED"],
        ),
        (
            "sf_after_closing",
            "7月24日19点去顺丰取件。",
            0,
            "partial",
            ["TASK_UNSCHEDULED"],
        ),
        (
            "northwest_sun_run_window",
            "7月24日下午去西北田径场完成40分钟阳光长跑。",
            1,
            "completed",
            ["API_DEGRADED"],
        ),
        (
            "sunday_dorm_gate",
            "7月26日晚上23点30分回宿舍洗澡30分钟。",
            0,
            "partial",
            ["TASK_UNSCHEDULED"],
        ),
        (
            "weekend_clinic_closing",
            "7月25日15点45分去校医院就诊30分钟。",
            0,
            "partial",
            ["TASK_UNSCHEDULED"],
        ),
        (
            "weekday_badminton",
            "7月24日下午打羽毛球1小时。",
            1,
            "completed",
            ["API_DEGRADED"],
        ),
        (
            "hdu_multi_constraint",
            (
                "7月24日第1至2节有课，下课后学习90分钟，"
                "17点30分前取京东快递，晚上跑步30分钟。"
            ),
            4,
            "completed",
            ["API_DEGRADED", "ROUTE_FALLBACK"],
        ),
    ]
    for (
        suffix,
        query,
        count,
        status,
        warning_codes,
    ) in hdu_constraint_cases:
        cases.append(
            chat_case(
                f"hdu_{suffix}",
                "hdu_constraints",
                query,
                min_task_count=count,
                expected_status=status,
                warning_codes=warning_codes,
            )
        )

    knowledge_cases = [
        (
            "library_floor_7",
            "图书馆七楼晚上几点关闭？",
            ["21:30"],
        ),
        (
            "library_overall",
            "图书馆每天最晚开放到几点？",
            ["22:30"],
        ),
        (
            "hot_water_morning",
            "宿舍早上什么时候有热水？",
            ["6:00", "8:00"],
        ),
        (
            "hot_water_evening",
            "晚上宿舍什么时候有热水？",
            ["16:30", "24:00"],
        ),
        (
            "dorm_gate_thursday",
            "周四晚上宿舍楼几点关门？",
            ["23:00"],
        ),
        (
            "dorm_gate_saturday",
            "周六晚上宿舍楼几点关门？",
            ["24:00"],
        ),
        (
            "sf_hours",
            "顺丰快递点每天几点关闭？",
            ["18:00"],
        ),
        (
            "jd_hours",
            "京东快递点每天几点关闭？",
            ["22:00"],
        ),
        (
            "cainiao_hours",
            "菜鸟驿站每天几点开门、几点关门？",
            ["8:30", "22:30"],
        ),
        (
            "clinic_weekend",
            "周末下午校医院几点可以就诊？",
            ["13:30", "16:00"],
        ),
    ]
    for suffix, query, markers in knowledge_cases:
        cases.append(
            chat_case(
                f"knowledge_{suffix}",
                "knowledge_qa",
                query,
                min_task_count=0,
                plan_status=None,
                warning_codes=[],
                answer_contains=markers + ["依据来源"],
                min_answer_length=30,
            )
        )

    temporal_cases = [
        chat_case(
            "temporal_course_block",
            "temporal_constraints",
            "明天第1至2节有高等数学课，下课后去图书馆自习1小时。",
            min_task_count=2,
            required_task_titles=["高等数学", "自习"],
        ),
        chat_case(
            "temporal_non_contiguous_courses",
            "temporal_constraints",
            "明天第1、3节有课，第4节以后去图书馆自习1小时。",
            min_task_count=3,
            required_task_titles=["课程", "自习"],
        ),
        chat_case(
            "temporal_fixed_meeting",
            "temporal_constraints",
            (
                "明天15:00到16:30固定参加社团会议，之后去取快递，"
                "18点前完成，再去图书馆自习1小时。"
            ),
            min_task_count=3,
            required_task_titles=["社团会议", "取快递", "自习"],
        ),
        chat_case(
            "temporal_sf_after_close",
            "temporal_constraints",
            "明天19点去顺丰快递取件，帮我看看能不能安排。",
            min_task_count=0,
            expected_status="partial",
            warning_codes=["OUTSIDE_OPENING_HOURS", "TASK_UNSCHEDULED"],
            answer_contains=["18:00", "不会擅自"],
        ),
        chat_case(
            "temporal_jd_before_close",
            "temporal_constraints",
            "明天21点去京东快递取件，帮我安排一下。",
            min_task_count=1,
            required_task_titles=["京东"],
        ),
        chat_case(
            "temporal_jd_after_close",
            "temporal_constraints",
            "明天21:45去京东快递取件，帮我看看能不能安排。",
            min_task_count=0,
            expected_status="partial",
            warning_codes=["OUTSIDE_OPENING_HOURS", "TASK_UNSCHEDULED"],
            answer_contains=["22:00"],
        ),
        chat_case(
            "temporal_library_boundary",
            "temporal_constraints",
            "明天22点去图书馆自习30分钟，可以吗？",
            min_task_count=0,
            plan_status=None,
            warning_codes=[],
            answer_contains=["22:30", "不同楼层"],
        ),
        chat_case(
            "temporal_northwest_run",
            "temporal_constraints",
            "明天下午去西北田径场完成40分钟阳光长跑。",
            min_task_count=1,
            required_task_titles=["阳光长跑"],
            answer_contains=["18:30"],
        ),
        chat_case(
            "temporal_sunday_curfew",
            "temporal_constraints",
            "7月26日晚上23点30分回宿舍洗澡30分钟。",
            min_task_count=0,
            expected_status="partial",
            warning_codes=["TASK_UNSCHEDULED"],
            answer_contains=["23:00"],
        ),
        chat_case(
            "temporal_weekend_clinic",
            "temporal_constraints",
            "7月25日15点45分去校医院就诊30分钟。",
            min_task_count=0,
            expected_status="partial",
            warning_codes=["TASK_UNSCHEDULED"],
            answer_contains=["16:00"],
        ),
    ]
    cases.extend(temporal_cases)

    resilience_cases = [
        chat_case(
            "care_infeasible",
            "resilience_care",
            (
                "明天17:30从第六教学楼出发，要去图书馆学习2小时、"
                "取快递、跑步30分钟，必须18点前全部结束。"
            ),
            min_task_count=0,
            expected_status="partial",
            warning_codes=["TASK_UNSCHEDULED"],
            answer_contains=["调整"],
            answer_not_contains=["你好"],
            min_answer_length=160,
        ),
        chat_case(
            "care_bicycle_mode",
            "resilience_care",
            (
                "明天14点从第六教学楼出发，骑自行车去图书馆自习1小时，"
                "再去菜鸟驿站取快递，18点前结束。"
            ),
            min_task_count=2,
            required_task_titles=["自习", "取快递"],
            required_travel_mode="bicycle",
        ),
        chat_case(
            "care_peak_congestion",
            "resilience_care",
            "明天15:55从图书馆出发，步行去菜鸟驿站取快递，17点前完成。",
            min_task_count=1,
            warning_codes=["API_DEGRADED", "PEAK_CONGESTION"],
            min_congestion_delay_min=1,
            answer_contains=["集中通行"],
        ),
        chat_case(
            "care_explicit_rain",
            "resilience_care",
            (
                "明天15点后先去东操场跑步30分钟，再去图书馆学习1小时，"
                "17点以后有雨，18点前结束。"
            ),
            min_task_count=2,
            required_task_titles=["跑步", "自习"],
            answer_contains=["17", "带把伞", "湿滑"],
        ),
        chat_case(
            "care_past_date",
            "resilience_care",
            "本周三去图书馆自习1小时。",
            min_task_count=0,
            expected_status="needs_clarification",
            plan_status=None,
            warning_codes=[],
            answer_contains=["已经过去"],
            answer_not_contains=["你好"],
        ),
        chat_case(
            "care_national_holiday",
            "resilience_care",
            "2026年国庆节什么时候放假？",
            min_task_count=0,
            plan_status=None,
            warning_codes=[],
            answer_contains=["10月1日", "10月7日", "10月10日", "学校"],
        ),
        chat_case(
            "care_adjusted_workday",
            "resilience_care",
            "2026年10月10日要上课吗？",
            min_task_count=0,
            plan_status=None,
            warning_codes=[],
            answer_contains=["调休工作日"],
            answer_not_contains=["确定要上课"],
        ),
        chat_case(
            "care_holiday_venue",
            "resilience_care",
            "2026年10月2日去图书馆自习1小时，再去东操场跑步30分钟。",
            min_task_count=1,
            expected_status="partial",
            warning_codes=["TASK_UNSCHEDULED"],
            required_task_titles=["跑步"],
            forbidden_task_titles=["图书馆自习"],
            answer_contains=["待调整", "门口"],
        ),
        chat_case(
            "care_ambiguous",
            "resilience_care",
            "最近事情有点多，帮我安排一下。",
            min_task_count=0,
            expected_status="needs_clarification",
            plan_status=None,
            warning_codes=[],
            answer_not_contains=["你好"],
            min_answer_length=40,
        ),
        chat_case(
            "care_handbook_grounding",
            "resilience_care",
            "学生考试作弊会受到什么处分？请按学生手册回答。",
            min_task_count=0,
            plan_status=None,
            warning_codes=[],
            answer_contains=["依据来源"],
            answer_not_contains=["当前知识库中没有检索到"],
            min_answer_length=80,
        ),
    ]
    cases.extend(resilience_cases)

    assert len(cases) == 112
    return cases


def main() -> None:
    output = BASE_DIR / "tests" / "fixtures" / "evaluation_cases.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_cases(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(build_cases())} cases: {output}")


if __name__ == "__main__":
    main()
