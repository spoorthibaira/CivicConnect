
import sqlite3
import psycopg
from database import get_db_connection

# Read existing SQLite data
sqlite_connection = sqlite3.connect("civicconnect.db")
sqlite_connection.row_factory = sqlite3.Row

users = sqlite_connection.execute(
    "SELECT * FROM users"
).fetchall()

# Connect to Supabase
supabase = get_db_connection()

try:
    for user in users:
        supabase.execute(
            """
            INSERT INTO users (id, name, email, password, role)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (email) DO NOTHING
            """,
            (
                user["id"],
                user["name"],
                user["email"],
                user["password"],
                user["role"]
            )
        )

    supabase.commit()
    print("User migration completed successfully!")

except Exception:
    supabase.rollback()
    raise

finally:
    sqlite_connection.close()
    supabase.close()
