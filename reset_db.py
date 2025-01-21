import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def reset_database():
    # Database connection parameters
    dbname = "autotrade"
    user = "postgres"
    password = "postgres"
    host = "localhost"

    # Connect to PostgreSQL server (to postgres database)
    conn = psycopg2.connect(
        dbname="postgres",
        user=user,
        password=password,
        host=host
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    try:
        # Drop existing connections to the database
        cur.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{dbname}'
            AND pid <> pg_backend_pid();
        """)

        # Drop database if exists
        cur.execute(f"DROP DATABASE IF EXISTS {dbname}")
        print(f"Dropped database '{dbname}' if it existed")

        # Create new database
        cur.execute(f"CREATE DATABASE {dbname}")
        print(f"Created new database '{dbname}'")

    finally:
        cur.close()
        conn.close()
        print("Database reset completed!")

if __name__ == "__main__":
    reset_database() 