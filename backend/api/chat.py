import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session

from database.mysql import get_db

from db_models.chat import ChatRecord

from services.rag import rag_chat, rag_chat_stream, rewrite_question
from utils.logger import logger
from services.agent import agent_chat_stream, agent_chat_with_plan_stream
from services.multi_agent import get_session_trace, multi_agent_chat, _route_intent

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
        sources=json.dumps(result["sources"], ensure_ascii=False),
        trace_data=json.dumps({"mode": "rag"}, ensure_ascii=False),
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
    accumulated = {"answer": "", "sources": [], "trace_data": {"mode": "rag_stream"}}

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
            sources=json.dumps(accumulated.get("sources", []), ensure_ascii=False),
            trace_data=json.dumps(accumulated.get("trace_data", {"mode": "stream"}), ensure_ascii=False),
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


@router.post("/chat/agent/stream")
async def chat_agent_stream(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Agent 流式聊天 — 实时展示工具调用和思考过程"""
    department = current_user["department"]
    accumulated = {"answer": "", "conversation_id": "", "trace_data": {"mode": "agent_stream"}}

    async def sse_generator():
        async for event_json in agent_chat_stream(
            request.question, department, request.conversation_id
        ):
            event = json.loads(event_json)
            if event["type"] == "done":
                accumulated["answer"] = event["answer"]
                accumulated["conversation_id"] = event.get("conversation_id", "")
                accumulated["trace_data"]["session_id"] = event.get("session_id", event.get("conversation_id", ""))
            yield f"data: {event_json}\n\n"

        record = ChatRecord(
            conversation_id=request.conversation_id,
            username=current_user["username"],
            department=department,
            question=request.question,
            answer=accumulated["answer"],
            sources=json.dumps([], ensure_ascii=False),
        )
        db.add(record)
        db.commit()

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/planner/stream")
async def chat_planner_stream(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Planner Agent — 先推计划, 再流式执行每一步"""
    department = current_user["department"]
    accumulated = {"answer": "", "plan": []}

    async def sse_generator():
        async for event_json in agent_chat_with_plan_stream(
            request.question, department, request.conversation_id
        ):
            event = json.loads(event_json)
            if event["type"] == "plan":
                accumulated["plan"] = event["data"]
            elif event["type"] == "done":
                accumulated["answer"] = event["answer"]
            yield f"data: {event_json}\n\n"

        # 保存聊天记录
        record = ChatRecord(
            conversation_id=request.conversation_id,
            username=current_user["username"],
            department=department,
            question=request.question,
            answer=accumulated["answer"],
            sources=json.dumps([], ensure_ascii=False),
        )
        db.add(record)
        db.commit()

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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


@router.post("/chat/multi-agent/stream")
async def chat_multi_agent_stream(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Multi-Agent 流式协作 — 5个Agent分工 + Reviewer审查"""
    department = current_user["department"]
    accumulated = {"answer": "", "session_id": "", "trace_data": {"mode": "multi_agent"}}

    async def sse_generator():
        async for event_json in multi_agent_chat(
            request.question, department
        ):
            event = json.loads(event_json)
            if event["type"] == "done":
                accumulated["answer"] = event["answer"]
                accumulated["session_id"] = event.get("session_id", "")
                accumulated["trace_data"]["session_id"] = event.get("session_id", "")
            yield f"data: {event_json}\n\n"

        record = ChatRecord(
            conversation_id=request.conversation_id,
            username=current_user["username"],
            department=department,
            question=request.question,
            answer=accumulated["answer"],
            sources=json.dumps([], ensure_ascii=False),
        )
        db.add(record)
        db.commit()

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/unified/stream")
async def chat_unified_stream(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """统一入口 — Query Rewrite → Router → RAG / Agent / Multi-Agent"""
    department = current_user["department"]

    # 加载历史, 用于 Query Rewrite
    history = (
        db.query(ChatRecord)
        .filter(ChatRecord.conversation_id == request.conversation_id)
        .order_by(ChatRecord.created_time)
        .all()
    )

    # Query Rewrite (失败降级: 用原问题)
    try:
        rewritten = await rewrite_question(request.question, history) if history else request.question
    except Exception:
        rewritten = request.question

    # Router (失败降级: 默认走 Agent)
    try:
        route, agent_type = await _route_intent(rewritten)
    except Exception:
        route, agent_type = "simple", "knowledge"

    accumulated = {"answer": "", "mode": "", "session_id": ""}

    async def sse_generator():
        mode_map = {"simple": agent_type, "complex": "multi-agent"}
        mode_name = mode_map.get(route, agent_type)
        yield f"data: {json.dumps({'type': 'route', 'mode': mode_name, 'agent': agent_type}, ensure_ascii=False)}\n\n"

        if route == "complex":
            # Multi-Agent 流程
            async for event_json in multi_agent_chat(rewritten, department):
                event = json.loads(event_json)
                if event["type"] == "done":
                    accumulated["answer"] = event["answer"]
                    accumulated["session_id"] = event.get("session_id", "")
                yield f"data: {event_json}\n\n"
            accumulated["mode"] = "multi-agent"
        else:
            async for event_json in agent_chat_stream(rewritten, department, request.conversation_id):
                event = json.loads(event_json)
                if event["type"] == "done":
                    accumulated["answer"] = event["answer"]
                    accumulated["session_id"] = event.get("conversation_id", "")
                yield f"data: {event_json}\n\n"
            accumulated["mode"] = mode_name

        record = ChatRecord(
            conversation_id=request.conversation_id,
            username=current_user["username"],
            department=department,
            question=request.question,
            answer=accumulated["answer"],
            sources=json.dumps([], ensure_ascii=False),
            trace_data=json.dumps(accumulated, ensure_ascii=False),
        )
        db.add(record)
        db.commit()

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/chat/trace/{session_id}")
def get_trace(session_id: str, current_user: dict = Depends(get_current_user)):
    """返回 Multi-Agent 完整执行树"""
    trace = get_session_trace(session_id)
    if not trace:
        return {"error": "session not found", "session_id": session_id}
    return trace