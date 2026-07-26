from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session

from database.mysql import get_db

from db_models.user import User

from services.dependency import get_current_user

from schemas.admin import ApproveUserRequest

from services.dependency import require_admin


router = APIRouter(
    prefix="/admin",
    tags=["admin"]
)



def check_admin(user):

    if user["role"] != "admin":

        raise HTTPException(
            status_code=403,
            detail="没有管理员权限"
        )



@router.get("/pending-users")
def get_pending_users(

    current_user=Depends(get_current_user),

    db: Session = Depends(get_db),

    admin=Depends(require_admin)

):

    check_admin(current_user)


    users = (
        db.query(User)
        .filter(
            User.status=="pending"
        )
        .all()
    )


    return users

@router.put("/approve-user/{username}")
def approve_user(
    username:str,
    data:ApproveUserRequest,
    db:Session=Depends(get_db),
    admin=Depends(require_admin)
):


    user = (
        db.query(User)
        .filter(
            User.username==username
        )
        .first()
    )


    if not user:
        return {
            "message":"用户不存在"
        }


    user.department=data.department

    user.status="active"


    db.commit()

    db.refresh(user)


    return {
        "message":"审核通过",
        "username":user.username,
        "department":user.department,
        "status":user.status
    }