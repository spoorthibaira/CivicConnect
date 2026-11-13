
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection
import psycopg


# Register a new citizen
def register_user(name, email, password):
    connection = get_db_connection()

    try:
        hashed_password = generate_password_hash(password)

        connection.execute(
            """
            INSERT INTO users (name, email, password)
            VALUES (%s, %s, %s)
            """,
            (name, email, hashed_password)
        )

        connection.commit()
        return True

    except psycopg.errors.UniqueViolation:
        connection.rollback()
        return False

    finally:
        connection.close()


# Login citizen
def login_user(email, password):
    connection = get_db_connection()

    try:
        user = connection.execute(
            "SELECT * FROM users WHERE email = %s",
            (email,)
        ).fetchone()

        if user and check_password_hash(user["password"], password):
            return user

        return None

    finally:
        connection.close()
