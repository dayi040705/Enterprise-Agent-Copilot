from openai import AsyncOpenAI

from config import DEEPSEEK_API_KEY, DEEPSEEK_MODEL
from utils.logger import logger
from core.exception import LLMException


client = AsyncOpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com",
    timeout=120,        # 流式回答可能超过 30 秒, 30 会掐断长回答
    max_retries=2,      # 网络抖动/429 自动重试
)


async def call_llm(messages):

    try:

        logger.info("开始调用LLM")


        response = await client.chat.completions.create(

            model=DEEPSEEK_MODEL,

            messages=messages

        )


        logger.info("LLM调用成功")


        return response.choices[0].message.content


    except Exception as e:

        logger.error(
            f"LLM调用失败:{e}"
        )

        raise LLMException()


async def call_llm_stream(messages):
    """流式调用 LLM — 一边生成一边推送 token, ChatGPT 同款打字机效果"""

    try:
        logger.info("开始流式调用LLM")

        stream = await client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=messages,
            stream=True,          # 开启流式
            stream_options={"include_usage": True}  # 包含 token 用量统计
        )

        async for chunk in stream:
            # 每个 chunk 是一个 Delta, 包含一个/几个 token
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

        logger.info("流式LLM调用完成")

    except Exception as e:
        logger.error(f"LLM流式调用失败:{e}")
        raise LLMException()