from fastapi import APIRouter, Depends, HTTPException
from database.mysql import SessionLocal
from db_models.user import User
from utils.password import hash_password


router = APIRouter()



@router.post("/register")
def register(
    username: str,
    password: str
):


    db = SessionLocal()


    # 1. 查询用户名是否存在

    exist_user = db.query(User).filter(
        User.username == username
    ).first()



    if exist_user:

        db.close()

        raise HTTPException(
            status_code=400,
            detail="用户名已经存在"
        )



    # 2. 创建新用户

    new_user = User(

        username=username,

        password_hash=hash_password(password),

        department=None,

        role="employee",

        status="pending"

    )



    db.add(new_user)

    db.commit()

    db.refresh(new_user)



    db.close()



    return {

        "message":"注册成功，等待管理员审核",

        "username":username

    }