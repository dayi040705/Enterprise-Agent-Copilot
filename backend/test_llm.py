import asyncio

from services.llm import call_llm


async def main():

    messages = [
        {
            "role":"user",
            "content":"什么是RAG?"
        }
    ]

    answer = await call_llm(messages)

    print(answer)


asyncio.run(main())