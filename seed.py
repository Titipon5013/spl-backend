import os
from dotenv import load_dotenv
from passlib.context import CryptContext
from db.session import SessionLocal
from db.models import Admin
from enums import RoleEnum, ApprovalStatus

load_dotenv()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def run_seed():
    db = SessionLocal()
    try:
        username = os.getenv("SEED_USERNAME")
        password = os.getenv("SEED_PASSWORD")
        email = os.getenv("SEED_EMAIL")

        if not username or not password:
            print("❌ ไม่พบตัวแปร SEED_USERNAME หรือ SEED_PASSWORD ใน Environment")
            return

        existing_admin = db.query(Admin).filter(Admin.username == username).first()
        if existing_admin:
            print(f"✅ มีบัญชี '{username}' อยู่ในฐานข้อมูลเรียบร้อยแล้ว ไม่ต้องสร้างซ้ำ")
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
        print(f"🎉 สร้างบัญชี Admin '{username}' สำเร็จแล้ว! เอาไปล็อกอินได้เลย")

    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาดระหว่างสร้าง Admin: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()