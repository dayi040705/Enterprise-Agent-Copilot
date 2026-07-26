from jose import jwt
from datetime import datetime, timedelta


SECRET_KEY = "enterprise-rag-secret"

ALGORITHM = "HS256"



def create_token(data):

    to_encode = data.copy()


    expire = datetime.utcnow() + timedelta(hours=2)


    to_encode.update(
        {
            "exp":expire
        }
    )


    token = jwt.encode(
        to_encode,
        SECRET_KEY,
        algorithm=ALGORITHM
    )


    return token



def decode_token(token):

    payload = jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM]
    )


    return payload