from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session

from database.mysql import get_db

from db_models.document import Document

from services.dependency import get_current_user

from services.chroma import delete_documents

from services.permission import require_role


router = APIRouter(
    prefix="/documents",
    tags=["documents"]
)



@router.get("")
def get_documents(

    current_user=Depends(get_current_user),

    db:Session=Depends(get_db)

):


    username = current_user["username"]

    department = current_user["department"]

    role = current_user["role"]



    if role == "admin":

        documents = (
        db.query(Document)
        .filter(
            Document.status=="active"
    )
        .all()
)


    else:

        documents = (
        db.query(Document)
        .filter(
            Document.department == department,
            Document.status=="active"
    )
        .all()
)


    return documents
@router.delete("/{document_id}")
def delete_document(

    document_id:int,

    current_user=Depends(
        require_role("admin")
    ),

    db:Session=Depends(get_db)

):


    


    document=(
        db.query(Document)
        .filter(
            Document.id==document_id
        )
        .first()
    )


    if not document:

        raise HTTPException(
            status_code=404,
            detail="文档不存在"
        )


    # 删除向量

    delete_documents(
        document.filename,
        document.version
    )


    # 软删除

    document.status="deleted"


    db.commit()


    return {

        "message":"删除成功",

        "filename":document.filename

    }

@router.patch("/{document_id}/disable")
def disable_document(

    document_id:int,

    current_user=Depends(get_current_user),

    db:Session=Depends(get_db)

):

    if current_user["role"]!="admin":

        raise HTTPException(
            status_code=403,
            detail="只有管理员可以操作"
        )


    document = (
        db.query(Document)
        .filter(
            Document.id==document_id
        )
        .first()
    )


    if not document:

        raise HTTPException(
            status_code=404,
            detail="文档不存在"
        )


    document.status="disabled"


    db.commit()


    return {
        "message":"文档已禁用"
    }
@router.patch("/{document_id}/enable")
def enable_document(

    document_id:int,

    current_user=Depends(get_current_user),

    db:Session=Depends(get_db)

):

    if current_user["role"]!="admin":

        raise HTTPException(
            status_code=403,
            detail="只有管理员可以操作"
        )


    document = (
        db.query(Document)
        .filter(
            Document.id==document_id
        )
        .first()
    )


    if not document:

        raise HTTPException(
            status_code=404,
            detail="文档不存在"
        )


    document.status="active"


    db.commit()


    return {
        "message":"文档已启用"
    }