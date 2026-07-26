from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from services.auth import decode_token


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/login"
)



# 普通用户身份解析
def get_current_user(
        token:str = Depends(oauth2_scheme)
):

    try:

        payload = decode_token(token)


        username = payload.get("username")
        department = payload.get("department")
        role = payload.get("role")


        if not username:
            raise HTTPException(
                status_code=401,
                detail="无效token"
            )


        return {
            "username":username,
            "department":department,
            "role":role
        }


    except Exception:

        raise HTTPException(
            status_code=401,
            detail="token失效"
        )




# 管理员权限检查
def require_admin(
        user=Depends(get_current_user)
):

    if user.get("role") != "admin":

        raise HTTPException(
            status_code=403,
            detail="没有管理员权限"
        )


    return user