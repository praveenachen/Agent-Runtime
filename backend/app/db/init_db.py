from app.db.session import Base, engine


def init_db() -> None:
    import app.models.job  # noqa: F401

    Base.metadata.create_all(bind=engine)

