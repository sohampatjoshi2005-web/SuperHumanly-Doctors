from app.db import get_session
from app.db_models import User
from sqlmodel import select

with get_session() as session:
    users = session.exec(select(User)).all()
    for u in users:
        print(f"User: {u.username}, Role: {u.role}")
