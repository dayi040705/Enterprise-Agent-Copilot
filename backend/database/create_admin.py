from database.mysql import SessionLocal
from db_models.user import User
from utils.password import hash_password


db = SessionLocal()


admin = User(
    username="admin",
    password_hash=hash_password("123456"),
    department="ADMIN",
    role="admin",
    status="active"
)


db.add(admin)

db.commit()

db.close()


print("管理员创建成功")