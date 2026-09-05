import sys
from sqlmodel import SQLModel
from sqlalchemy import inspect
from app.db import engine
from app.db_models import UsageMeter, UpgradeRequest

def check_schema():
    # Ensure all tables are created
    SQLModel.metadata.create_all(engine)
    
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Detected tables: {tables}")
    
    success = True
    if "usagemeter" in tables:
        print("✅ Success: UsageMeter table found.")
    else:
        print("❌ Error: UsageMeter table NOT found.")
        success = False
        
    if "upgraderequest" in tables:
        print("✅ Success: UpgradeRequest table found.")
    else:
        print("❌ Error: UpgradeRequest table NOT found.")
        success = False
        
    return success

if __name__ == "__main__":
    if check_schema():
        sys.exit(0)
    else:
        sys.exit(1)
