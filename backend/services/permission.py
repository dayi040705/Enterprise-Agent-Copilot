from fastapi import HTTPException, Depends

from services.dependency import get_current_user



def require_role(required_role):

    def checker(
        current_user=Depends(get_current_user)
    ):

        if current_user["role"] != required_role:

            raise HTTPException(
                status_code=403,
                detail="权限不足"
            )

        return current_user


    return checker