import json

from services.llm import call_llm, call_llm_stream
from utils.logger import logger
from services.hybrid import hybrid_search
from services.prompt import (
    RAG_SYSTEM_PROMPT,
    RAG_USER_TEMPLATE,
    QUERY_REWRITE_SYSTEM_PROMPT,
    QUERY_REWRITE_USER_TEMPLATE,
)


async def rag_chat(
        question,
        department,
        history=None
):
    if history is None:
        history=[]


    history_text=""


    for item in history:

        history_text += f"""
    用户:
    {item.question}

    助手:
    {item.answer}

    """
    search_question = await rewrite_question(
        question,
        history
    )
    logger.info(
    f"Query Rewrite: {question} -> {search_question}"
    )


    contexts = hybrid_search(
        search_question,
        department
    )

    if not contexts:

      return {
        "answer":"没有找到相关资料",
        "sources":[]
    }


    context_text = ""

    sources = []


    for item in contexts:


        context_text += (
            "\n"
            + item["text"]
            + "\n"
        )


        source_info = {
    "source": item["metadata"].get("filename"),
    "page": item["metadata"].get("page",0),
    "content": item["text"]
}


        sources.append(
          source_info
)



    messages = [

        {
            "role":"system",
            "content": RAG_SYSTEM_PROMPT
        },


        {
            "role":"user",
            "content": RAG_USER_TEMPLATE.format(
                history_section=f"历史对话:\n\n{history_text}\n\n" if history_text else "",
                context_text=context_text,
                question=question,
            )
        }

    ]


    answer = await call_llm(
        messages
    )


    return {
        "answer":answer,
        "sources":sources
    }   

async def rewrite_question(
        question,
        history
):


    if not history:

        return question


    history_text = ""


    for item in history[-5:]:

        history_text += f"""
用户:
{item.question}

助手:
{item.answer}

"""


    messages=[

        {
            "role":"system",
            "content": QUERY_REWRITE_SYSTEM_PROMPT
        },


        {
            "role":"user",
            "content": QUERY_REWRITE_USER_TEMPLATE.format(
                history_text=history_text,
                question=question,
            )
        }

    ]


    return await call_llm(
        messages
    )


async def rag_chat_stream(
        question,
        department,
        history=None
):
    """流式 RAG 回答 — 检索结果一次性返回, LLM 回答逐字推送"""
    if history is None:
        history = []

    # 1. 查询改写 (与普通版相同)
    history_text = ""
    for item in history:
        history_text += f"用户: {item.question}\n助手: {item.answer}\n"

    search_question = await rewrite_question(question, history)
    logger.info(f"Query Rewrite: {question} -> {search_question}")

    # 2. 检索 + 构建 sources (与普通版相同)
    contexts = hybrid_search(search_question, department)

    if not contexts:
        # 无结果时推送一次, 走 SSE 的 data 通道
        yield json.dumps({"type": "done", "answer": "没有找到相关资料", "sources": []}, ensure_ascii=False)
        return

    context_text = ""
    sources = []
    for item in contexts:
        context_text += "\n" + item["text"] + "\n"
        sources.append({
            "source": item["metadata"].get("filename"),
            "page": item["metadata"].get("page", 0),
            "content": item["text"],
        })

    # 3. 先推送 sources (前端可以先展示引用来源)
    yield json.dumps({"type": "sources", "data": sources}, ensure_ascii=False)

    # 4. 构建 messages 并流式推送 LLM 回答
    messages = [
        {
            "role": "system",
            "content": RAG_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": RAG_USER_TEMPLATE.format(
                history_section=f"历史对话:\n\n{history_text}\n\n" if history_text else "",
                context_text=context_text,
                question=question,
            ),
        },
    ]

    full_answer = ""
    async for token in call_llm_stream(messages):
        full_answer += token
        yield json.dumps({"type": "token", "data": token}, ensure_ascii=False)

    # 5. 推送结束标记 + 完整 answer
    yield json.dumps({"type": "done", "answer": full_answer, "sources": sources}, ensure_ascii=False)
