import subprocess
from app.core.config import settings


def main():
    uri = settings.MONGO_DB_URL
    db_name = settings.MONGO_DB_NAME
    migrations_path = "app/migrations"

    print(f"Run migrations: {db_name}")

    result = subprocess.run(
        [
            "beanie",
            "migrate",
            "-uri",
            uri,
            "-db",
            db_name,
            "-p",
            migrations_path,
        ]
    )

    if result.returncode == 0:
        print("Migrated")
    else:
        print("Error")


if __name__ == "__main__":
    main()
