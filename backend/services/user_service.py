from sqlalchemy.orm import Session

from db_models.user import User

from utils.password import verify_password



def authenticate(
    db:Session,
    username:str,
    password:str
):

    user = (
        db.query(User)
        .filter(
            User.username==username
        )
        .first()
    )


    if not user:
        return None


    if not verify_password(
        password,
        user.password_hash
    ):
        return None


    return user