from fastapi import HTTPException


class LLMException(HTTPException):

    def __init__(self):

        super().__init__(
            status_code=500,
            detail="AI服务暂时不可用，请稍后重试"
        )