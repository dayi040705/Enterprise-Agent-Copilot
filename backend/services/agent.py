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
    {
        "type": "function", "function": {
            "name": "search_knowledge_base",
            "description": "搜索企业知识库: 制度/流程/技术文档/通讯录。可多次调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "department": {"type": "string", "enum": ["HR", "TECH"]}
                },
                "required": ["query", "department"]
            }
        }
    },
    {
        "type": "function", "function": {
            "name": "search_logs",
            "description": "搜索服务器运行日志, 分析错误原因。",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string", "description": "服务名: user-service/order-service/payment-service"},
                    "keyword": {"type": "string", "description": "关键词, 如 ERROR/timeout"}
                },
                "required": ["service"]
            }
        }
    },
    {
        "type": "function", "function": {
            "name": "search_memory",
            "description": "搜索历史故障处理经验库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "问题描述"},
                    "department": {"type": "string", "enum": ["HR", "TECH"]}
                },
                "required": ["query", "department"]
            }
        }
    },
    {
        "type": "function", "function": {
            "name": "query_database",
            "description": "查询企业业务数据库: 员工信息(employees)、IT工单(tickets)、"
                           "请假记录(leave_records)。可指定表名+姓名/部门/状态过滤。",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "表名: employees / tickets / leave_records"},
                    "name": {"type": "string", "description": "员工姓名, 如'张三'"},
                    "dept": {"type": "string", "description": "部门: HR / TECH / ADMIN"},
                    "status": {"type": "string", "description": "状态: 已解决 / 处理中 / 待审批"}
                },
                "required": ["table"]
            }
        }
    }
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
