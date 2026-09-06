from getpass import getpass

from backend.auth import hash_password
from backend.database import SessionLocal
from backend.models import User


def create_user(username: str, password: str):
    db = SessionLocal()

    try:
        existing = (
            db.query(User)
            .filter(User.username == username)
            .first()
        )

        if existing:
            print(f"User '{username}' already exists.")
            return

        user = User(
            username=username,
            password_hash=hash_password(password),
            is_active=1,
        )

        db.add(user)
        db.commit()

        print(f"User '{username}' created successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    print("URBANFLOW USER CREATION")
    print("-----------------------")

    username = input("Username: ").strip()

    if not username:
        print("Username cannot be empty.")
        raise SystemExit(1)

    password = getpass("Password: ")
    confirm_password = getpass("Confirm password: ")

    if password != confirm_password:
        print("Passwords do not match.")
        raise SystemExit(1)

    if len(password) < 8:
        print("Password must be at least 8 characters.")
        raise SystemExit(1)

    create_user(username, password)