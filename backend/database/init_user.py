from database.mysql import SessionLocal

from db_models.user import User

from utils.password import hash_password



db = SessionLocal()



users=[

    User(
        username="zhangsan",
        password_hash=hash_password("123456"),
        department="HR",
        role="employee"
    ),


    User(
        username="lisi",
        password_hash=hash_password("123456"),
        department="TECH",
        role="employee"
    ),

    User(
        username="admin",
        password_hash=hash_password("admin123"),
        department="ADMIN",
        role="admin",
        status="active"
    )

]


db.add_all(users)

db.commit()

db.close()


print("用户初始化完成")