"""
ReAct Agent 核心 + Planner — LLM 推理 + 工具调用编排

依赖:
  executor.py — 工具注册、参数校验、执行
  TOOLS 列表 — OpenAI Function Calling 格式的工具描述
"""
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

# ── TOOLS (OpenAI 格式, 给 LLM 看的菜单) ──

TOOLS = [
    # ── 知识库 + 日志 + 记忆 (保持不变) ──
    {
        "type": "function", "function": {
            "name": "search_knowledge_base",
            "description": "搜索电商运营SOP: 售后处理/广告投放/Listing优化/跟卖应对/库存管理。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "department": {"type": "string", "enum": ["HR", "TECH", "运营部", "客服部", "供应链部"]}
                },
                "required": ["query", "department"]
            }
        }
    },
    {
        "type": "function", "function": {
            "name": "search_logs",
            "description": "搜索电商服务日志。服务: sp-api(数据管道)/order-service(订单)/payment-service(支付)/inventory-service(库存)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "服务名"},
                    "keyword": {"type": "string", "description": "关键词, 如 ERROR/timeout"}
                },
                "required": ["service"]
            }
        }
    },
    {
        "type": "function", "function": {
            "name": "search_memory",
            "description": "搜索历史运营经验库: 差评处理/断货补货/跟卖应对经验。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "问题描述"},
                    "department": {"type": "string", "enum": ["HR", "TECH", "运营部", "客服部", "供应链部"]}
                },
                "required": ["query", "department"]
            }
        }
    },
    # ── 数据查询 (参数化,不用写SQL) ──
    {
        "type": "function", "function": {
            "name": "query_orders",
            "description": "查订单状态。参数: status(delivered/canceled/空=全部), limit(默认10)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "description": "订单状态: delivered/canceled/空=全部"},
                    "limit": {"type": "integer", "description": "返回条数, 默认10"}
                }
            }
        }
    },
    {
        "type": "function", "function": {
            "name": "query_analytics",
            "description": "查销量/退款率趋势(OLAP预聚合,毫秒级)。查退款率Top N/销量排行/库存预警都用这个工具!别自己写SQL!",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": ["top_refund", "top_sales", "low_stock", "trend"],
                               "description": "查询类型: top_refund=退款率排行/top_sales=销量排行/low_stock=库存预警/trend=趋势"},
                    "limit": {"type": "integer", "description": "返回条数, 默认5"}
                }
            }
        }
    },
    {
        "type": "function", "function": {
            "name": "query_listing",
            "description": "查Listing评分/评价数/健康度。",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "可选, 指定SKU"},
                    "category": {"type": "string", "description": "可选, 按品类筛选"},
                    "limit": {"type": "integer", "description": "返回条数, 默认10"}
                }
            }
        }
    },
    {
        "type": "function", "function": {
            "name": "query_sync_logs",
            "description": "查SP-API数据管道同步健康度(录入率/失败原因)。",
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": {"type": "integer", "description": "查最近多少小时, 默认24"}
                }
            }
        }
    },
]

# ── Schema ──

class TaskStatus(str, Enum):
    PENDING = "pending"; IN_PROGRESS = "in_progress"; COMPLETED = "completed"; FAILED = "failed"

class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{datetime.now().timestamp()}")
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    tool_name: str | None = None
    tool_args: dict | None = None
    result_preview: str | None = None

class AgentResult(BaseModel):
    answer: str = ""; mode: str = ""; conversation_id: str = ""
    tasks: list[Task] = []; plan: list[str] = []; turns: int = 0; total_calls: int = 0

# ── 委托给 LangGraph: 所有 Agent 函数现在只是 graph.py 的包装 ──

from services.graph import (
    run_agent,
    run_agent_stream_tokens,
    run_agent_with_plan,
    run_structured_planner_stream,
)


async def agent_chat(user_message: str, department: str = "HR",
                     conversation_id: str = "", **kwargs) -> AgentResult:
    """ReAct Agent (委托给 LangGraph)"""
    r = await run_agent(user_message, department, conversation_id)
    return AgentResult(answer=r["answer"], mode="react",
                       conversation_id=r["conversation_id"],
                       total_calls=r["total_calls"])


async def agent_chat_stream(user_message: str, department: str = "HR",
                             conversation_id: str = "", **kwargs):
    """ReAct Agent 流式 — 逐 token 推送"""
    async for event_json in run_agent_stream_tokens(user_message, department, conversation_id):
        yield event_json


async def agent_chat_with_plan(user_message: str, department: str = "HR",
                               conversation_id: str = "", **kwargs) -> AgentResult:
    """Planner Agent (委托给 LangGraph)"""
    r = await run_agent_with_plan(user_message, department, conversation_id)
    return AgentResult(answer=r["answer"], mode="planner",
                       conversation_id=r["conversation_id"],
                       plan=r.get("plan", []),
                       total_calls=r["total_calls"])


async def agent_chat_with_plan_stream(user_message: str, department: str = "HR",
                                       conversation_id: str = "", **kwargs):
    """结构化 Planner: JSON Task → Executor → Analyzer 闭环"""
    async for event_json in run_structured_planner_stream(
        user_message, department, conversation_id):
        yield event_json
