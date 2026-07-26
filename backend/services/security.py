from fastapi import Depends, HTTPException
from services.dependency import get_current_user



def require_admin(
    user=Depends(get_current_user)
):

    if user.get("role") != "admin":

        raise HTTPException(
            status_code=403,
            detail="需要管理员权限"
        )


    return user