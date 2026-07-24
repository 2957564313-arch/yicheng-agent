from app.config import get_settings
from app.repositories.database import Database


def main() -> None:
    settings = get_settings()
    database = Database(settings.app_database_path)
    database.initialize()
    print(f"initialized: {settings.app_database_path}")


if __name__ == "__main__":
    main()

