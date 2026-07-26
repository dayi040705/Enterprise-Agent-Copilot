from pydantic import BaseModel


class SessionResponse(BaseModel):

    conversation_id:str