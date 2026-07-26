from pydantic import BaseModel


class ApproveUserRequest(BaseModel):

    department: str