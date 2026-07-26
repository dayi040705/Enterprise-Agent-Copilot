from fastapi import APIRouter, Depends
import uuid

from services.dependency import get_current_user


router = APIRouter(
    prefix="/chat",
    tags=["chat"]
)



@router.post("/session")
def create_session(

    current_user=Depends(get_current_user)

):


    conversation_id = str(
        uuid.uuid4()
    )


    return {

        "conversation_id":
        conversation_id

    }