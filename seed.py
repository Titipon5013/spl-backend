import os
from dotenv import load_dotenv
from passlib.context import CryptContext
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models import Admin
from enums import RoleEnum, ApprovalStatus

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "postgresql+psycopg2://postgres:password@postgres:5432/smartparkinglot"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def run_seed():
    db = SessionLocal()
    try:
        username = os.getenv("SEED_USERNAME", "admin")
        password = os.getenv("SEED_PASSWORD", "admin123")
        email = os.getenv("SEED_EMAIL", "admin@gmail.com")

        existing_admin = db.query(Admin).filter(Admin.username == username).first()
        if existing_admin:
            print(f"✅ มีบัญชี '{username}' อยู่ในฐานข้อมูลเรียบร้อยแล้ว")
            return

        hashed_password = pwd_context.hash(password)
        new_admin = Admin(
            username=username,
            password_hash=hashed_password,
            email=email,
            role=RoleEnum.admin,
            approval_status=ApprovalStatus.approved
        )
        db.add(new_admin)
        db.commit()
        print(f"🎉 สร้างบัญชี Admin '{username}' สำเร็จแล้ว!")
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาด: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    run_seed()