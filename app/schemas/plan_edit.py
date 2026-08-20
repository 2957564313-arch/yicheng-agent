from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PlanEditOperation(BaseModel):
    """One change to make to a plan that already exists.

    The model describes the change; applying it is deterministic.  Asking the
    model to re-emit the whole day instead loses the parts it was not thinking
    about — which is exactly what “把自习换到下午，其他照旧” must not do.
    """

    model_config = ConfigDict(extra="forbid")

    action: Literal["move", "shorten", "lengthen", "remove", "add"]
    task_ref: str | None = Field(
        default=None,
        max_length=120,
        description=(
            "要改动的任务，用它在计划里的标题或 id 指代。"
            "用户说“这个/那件事”时，结合对话历史判断指的是哪一项。"
        ),
    )
    target_period: str | None = Field(
        default=None,
        max_length=40,
        description="移动到的时段：morning/afternoon/evening/day。",
    )
    target_start: datetime | None = Field(
        default=None,
        description="移动到的具体开始时刻，必须带 +08:00。",
    )
    target_date: date | None = Field(
        default=None,
        description="移动到的日期，用于“跑步换到明天”这类跨天调整。",
    )
    duration_min: int | None = Field(
        default=None,
        ge=5,
        le=720,
        description="shorten/lengthen/add 时的新时长。",
    )
    title: str | None = Field(
        default=None,
        max_length=120,
        description="action=add 时新任务的名称。",
    )
    location_raw: str | None = Field(default=None, max_length=120)


class PlanEdit(BaseModel):
    """What the student wants changed about the day they already have."""

    model_config = ConfigDict(extra="forbid")

    operations: list[PlanEditOperation] = Field(default_factory=list)
    keep_others_unchanged: bool = Field(
        default=True,
        description=(
            "除被点名的任务外，其余安排是否保持不变。"
            "用户说“其他照旧/其余不变”时为 true；"
            "只有用户要求重排一整天时才为 false。"
        ),
    )
    clarifications: list[str] = Field(default_factory=list)
