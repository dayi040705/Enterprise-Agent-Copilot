from fastapi import APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from fastapi import Depends
from fastapi import HTTPException

from services.user_service import authenticate
from services.auth import create_token
from database.mysql import get_db
from sqlalchemy.orm import Session


router = APIRouter()



@router.post("/login")
async def login(

    form_data:OAuth2PasswordRequestForm=Depends(),

    db:Session=Depends(get_db)

):


    user=authenticate(

        db,

        form_data.username,

        form_data.password

    )


    if not user:

        return {
            "message":"用户名密码错误"
        }



    token=create_token({

        "username":user.username,

        "department":user.department,

        "role":user.role

    })


    return {

        "access_token":token,

        "token_type":"bearer"

    }