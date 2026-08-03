class RepositoryConcurrencyError(RuntimeError):
    """A repository write lost an optimistic-concurrency race."""


class WeeklyPlanSuperseded(RepositoryConcurrencyError):
    """The target weekly plan is no longer the latest version."""


class WeeklyPlanSnapshotChanged(RepositoryConcurrencyError):
    """The latest baseline changed after a replan was computed."""


class WeeklyGroundingSnapshotChanged(RepositoryConcurrencyError):
    """Weekly allocations changed while a daily plan was being computed."""
