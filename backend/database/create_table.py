from database.mysql import engine, Base

from db_models.user import User
from db_models.document import Document


Base.metadata.create_all(
    engine
)


print("数据库表创建完成")