from datetime import date, datetime

from app.repositories.database import Database
from app.repositories.plans import PlanRepository
from app.schemas.common import PlanStatus
from app.schemas.plan import Plan, PlanItem, PlanMetrics


def test_database_initialization_is_idempotent(temp_database):
    temp_database.initialize()
    temp_database.initialize()


def test_database_initialization_releases_file_handle(tmp_path):
    database_path = tmp_path / "initialization.sqlite"
    Database(database_path).initialize()

    database_path.unlink()
    assert not database_path.exists()


def test_connection_context_releases_file_handle(tmp_path):
    database_path = tmp_path / "connection.sqlite"
    database = Database(database_path)
    with database.connect() as connection:
        connection.execute("CREATE TABLE example (id INTEGER PRIMARY KEY)")

    database_path.unlink()
    assert not database_path.exists()


def test_plan_roundtrip(temp_database, tz):
    repository = PlanRepository(temp_database)
    now = datetime(2026, 7, 23, 20, 0, tzinfo=tz)
    repository.ensure_user_and_thread(
        user_id="user_1",
        thread_id="thread_1",
        now=now,
    )
    plan = Plan(
        id="plan_1",
        user_id="user_1",
        thread_id="thread_1",
        date=date(2026, 7, 24),
        status=PlanStatus.VALID,
        version=1,
        items=[
            PlanItem(
                id="item_1",
                task_id="task_1",
                item_type="task",
                title="自习",
                start_at=datetime(2026, 7, 24, 14, 0, tzinfo=tz),
                end_at=datetime(2026, 7, 24, 16, 0, tzinfo=tz),
                location_id="library",
            )
        ],
        metrics=PlanMetrics(
            scheduled_task_count=1,
            requested_task_count=1,
        ),
        created_at=now,
    )
    repository.save(plan)

    loaded = repository.get("plan_1")
    assert loaded == plan
