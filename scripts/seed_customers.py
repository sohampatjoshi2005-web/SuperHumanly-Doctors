import asyncio
from app.db_mongodb import init_mongodb
from app.models.user import User
from app.db import get_session
from app.db_models import Customer
from sqlmodel import select

async def seed():
    await init_mongodb()
    
    # Get the admin user
    admin = await User.find_one(User.username == "admin")
    if not admin:
        print("Admin user not found. Please run the backend first to seed the admin.")
        return

    doctor_id = str(admin.id)
    print(f"Seeding customers for doctor: {admin.username} ({doctor_id})")

    customers = [
        "James Logan",
        "Sarah Parker",
        "Michael Scott",
        "Elena Gilbert",
        "Bruce Wayne"
    ]

    with get_session() as session:
        # Check if already seeded
        existing = session.exec(select(Customer).where(Customer.doctor_id == doctor_id)).all()
        if existing:
            print(f"Doctor already has {len(existing)} customers. Skipping seeding.")
            return

        for name in customers:
            customer = Customer(name=name, doctor_id=doctor_id)
            session.add(customer)
        
        session.commit()
        print(f"Successfully seeded {len(customers)} customers.")

if __name__ == "__main__":
    asyncio.run(seed())
