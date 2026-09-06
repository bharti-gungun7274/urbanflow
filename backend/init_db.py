from backend.database import Base, engine
import backend.models  # noqa: F401


def init_database():
    print("Tables registered:", list(Base.metadata.tables.keys()))

    Base.metadata.create_all(bind=engine)

    print("URBANFLOW DATABASE TABLES CREATED")


if __name__ == "__main__":
    init_database()