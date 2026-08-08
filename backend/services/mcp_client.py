"""
MCP Client — Agent 调用 MCP Server 工具的统一入口

6 个 MCP Server, 对标的 JD:
  query_orders    → "订单、销量数据"
  query_analytics → "数据查询、分析"
  query_inventory → "库存数据"
  query_listing   → "Listing、评论数据"
  query_sync_logs → "系统日志、数据链路问题"
  search_sop      → "业务规则和测试记录"
"""
import sys, os

MCP_TOOLS = {
    "query_orders": {
        "server": "query_orders_server",
        "desc": "查订单状态/退款/异常",
        "module": "mcp_servers.query_orders_server",
        "func": "query_orders",
    },
    "query_analytics_top_refund": {
        "server": "query_analytics_server",
        "desc": "查退款率最高的 Top N SKU",
        "module": "mcp_servers.query_analytics_server",
        "func": "query_top_refund_skus",
    },
    "query_analytics_sales": {
        "server": "query_analytics_server",
        "desc": "查日销量趋势/均价变化",
        "module": "mcp_servers.query_analytics_server",
        "func": "query_sales_trend",
    },
    "query_inventory": {
        "server": "query_inventory_server",
        "desc": "查库存预警/安全库存",
        "module": "mcp_servers.query_inventory_server",
        "func": "query_low_stock",
    },
    "query_listing_health": {
        "server": "query_listing_server",
        "desc": "查 Listing 评分/评价数/健康度",
        "module": "mcp_servers.query_listing_server",
        "func": "query_listing_health",
    },
    "query_listing_rating_drop": {
        "server": "query_listing_server",
        "desc": "查评分下降的 Listing 预警",
        "module": "mcp_servers.query_listing_server",
        "func": "query_rating_drop",
    },
    "query_sync_health": {
        "server": "query_sync_logs_server",
        "desc": "查数据管道录入率/延迟/失败原因",
        "module": "mcp_servers.query_sync_logs_server",
        "func": "query_sync_health",
    },
    "search_sop": {
        "server": "search_sop_server",
        "desc": "搜电商运营 SOP (售后/广告/Listing/跟卖/库存)",
        "module": "mcp_servers.search_sop_server",
        "func": "search_sop",
    },
}


def call_mcp_tool(tool_name: str, args: dict) -> str:
    """调用 MCP Server 工具 (开发环境: 本地导入, 生产环境: JSON-RPC)"""
    if tool_name not in MCP_TOOLS:
        return f"[MCP] 未知工具: {tool_name}. 可用: {list(MCP_TOOLS.keys())}"

    info = MCP_TOOLS[tool_name]
    try:
        module = __import__(info["module"], fromlist=[info["func"]])
        func = getattr(module, info["func"])
        return func(**args)
    except Exception as e:
        return f"[MCP {tool_name} 异常] {e}"


def get_mcp_tool_count() -> int:
    return len(MCP_TOOLS)
