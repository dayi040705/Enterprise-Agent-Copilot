from fastapi import APIRouter, UploadFile, File, Depends

from services.document import load_document
from services.splitter import split_text
from services.chroma import add_documents, delete_documents

from sqlalchemy.orm import Session

from database.mysql import get_db

from db_models.document import Document

from services.dependency import get_current_user

import shutil


router = APIRouter()



@router.post("/upload")
async def upload_file(

        file: UploadFile = File(...),

        current_user=Depends(get_current_user),

        db:Session=Depends(get_db)

):


    username = current_user["username"]

    department = current_user["department"]



    # ==========================
    # 1. 检查历史版本
    # ==========================


    old_document = (
        db.query(Document)
        .filter(
            Document.filename == file.filename,
            Document.department == department,
            Document.status=="active"
        )
        .first()
    )


    version = 1


    if old_document:


        # 删除旧向量

        delete_documents(
            old_document.filename,
            old_document.version
        )


        # 旧版本失效

        old_document.status="deleted"


        version = old_document.version + 1



    # ==========================
    # 2. 保存文件
    # ==========================


    file_path = f"./data/{file.filename}"


    with open(
        file_path,
        "wb"
    ) as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )



    # ==========================
    # 3. 文档解析
    # ==========================


    pages = load_document(
        file_path
    )



    chunks = split_text(

        pages,

        file.filename,

        department,

        version,

        "active"

    )



    # ==========================
    # 4. 写入向量库
    # ==========================


    add_documents(
        chunks
    )



    # ==========================
    # 5. 保存新版本记录
    # ==========================


    document = Document(

        filename=file.filename,

        department=department,

        uploader=username,

        chunk_count=len(chunks),

        version=version,

        status="active"

    )


    db.add(document)

    db.commit()



    return {

        "filename":file.filename,

        "department":department,

        "version":version,

        "chunks":len(chunks)

    }