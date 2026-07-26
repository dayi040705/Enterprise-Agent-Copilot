import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session

from database.mysql import get_db

from db_models.chat import ChatRecord

from services.rag import rag_chat, rag_chat_stream

from schemas.chat import ChatRequest

from services.dependency import get_current_user

import json




router = APIRouter()



@router.post("/chat")
async def chat(

    request:ChatRequest,

    current_user:dict = Depends(get_current_user),

    db:Session = Depends(get_db)

):


    username = current_user["username"]

    department = current_user["department"]
    
    history = (

        db.query(ChatRecord)

        .filter(

            ChatRecord.conversation_id
            ==
            request.conversation_id

        )

        .order_by(
            ChatRecord.created_time
        )

        .all()

    )
    result = await rag_chat(
        request.question,
        department,
        history
    )

    record = ChatRecord(
        conversation_id=request.conversation_id,
        username=username,
        department=department,
        question=request.question,
        answer=result["answer"],
        sources=json.dumps(
            result["sources"],
            ensure_ascii=False
        )
    )

    db.add(record)
    db.commit()

    return result


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    SSE 流式聊天 — ChatGPT 同款打字机效果

    前端使用方式 (JS):
      const eventSource = new EventSource('/chat/stream');
      eventSource.onmessage = (event) => {
        const { type, data } = JSON.parse(event.data);
        if (type === 'token') appendText(data);
        if (type === 'sources') showSources(data);
        if (type === 'done') finalize();
      };
    """
    username = current_user["username"]
    department = current_user["department"]

    history = (
        db.query(ChatRecord)
        .filter(ChatRecord.conversation_id == request.conversation_id)
        .order_by(ChatRecord.created_time)
        .all()
    )

    # 闭包变量 — 在流中累积完整回答, 结束时写 DB
    accumulated = {"answer": "", "sources": []}

    async def sse_generator():
        async for event_json in rag_chat_stream(
            request.question, department, history
        ):
            event = json.loads(event_json)

            if event["type"] == "sources":
                accumulated["sources"] = event["data"]

            elif event["type"] == "done":
                accumulated["answer"] = event["answer"]
                accumulated["sources"] = event.get("sources", accumulated["sources"])

            # SSE 格式: "data: {json}\n\n"
            yield f"data: {event_json}\n\n"
            # 强制事件循环 flush, 防止 uvicorn 缓冲多个 SSE 事件
            await asyncio.sleep(0)

        # 流结束后保存聊天记录
        record = ChatRecord(
            conversation_id=request.conversation_id,
            username=username,
            department=department,
            question=request.question,
            answer=accumulated["answer"],
            sources=json.dumps(accumulated["sources"], ensure_ascii=False),
        )
        db.add(record)
        db.commit()

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


@router.get("/chat/history")
def chat_history(

    current_user:dict = Depends(get_current_user),

    db:Session = Depends(get_db)

):


    username = current_user["username"]

    department = current_user["department"]

    role = current_user["role"]



    if role == "admin":

        records = (
            db.query(ChatRecord)
            .order_by(
                ChatRecord.created_time.desc()
            )
            .all()
        )


    else:

        records = (
            db.query(ChatRecord)
            .filter(
                ChatRecord.username == username
            )
            .order_by(
                ChatRecord.created_time.desc()
            )
            .all()
        )


    return records