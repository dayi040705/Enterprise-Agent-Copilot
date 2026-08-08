"""
MCP Server: search_sop
搜售后/广告/跟卖处理标准流程 — 封装 RAG 知识库检索
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.hybrid import hybrid_search


def search_sop(query: str, department: str = "TECH", top_k: int = 3) -> str:
    """搜电商运营 SOP: 售后流程/广告策略/Listing优化/跟卖应对/库存管理

    参数:
      query:      搜索关键词 (如 "退货怎么处理"、"广告ACOS怎么控制")
      department: 部门, 默认 TECH
      top_k:      返回条数
    """
    try:
        results = hybrid_search(query.strip(), department, top_k=top_k)
        if not results:
            return f"[search_sop] 未找到与 '{query}' 相关的 SOP。可用关键词: 退货/广告/跟卖/库存/Listing"

        lines = [f"[search_sop | MCP] '{query}' 相关 SOP (共 {len(results)} 条):"]
        for i, r in enumerate(results):
            src = r["metadata"].get("filename", "未知")
            page = r["metadata"].get("page", "?")
            lines.append(f"[{i+1}] 来源:{src} (第{page}页)\n{r['text'][:300]}")
        return "\n\n".join(lines)
    except Exception as e:
        # Reranker 可能挂, 降级到纯向量搜索
        try:
            from services.retriever import vector_search
            results = vector_search(query, department, top_k=top_k)
            if not results:
                return f"[search_sop] 未找到与 '{query}' 相关的 SOP"
            lines = [f"[search_sop | MCP] '{query}' 相关 (降级模式, {len(results)} 条):"]
            for i, r in enumerate(results):
                src = r["metadata"].get("filename", "未知")
                lines.append(f"[{i+1}] {src}: {r['text'][:200]}")
            return "\n".join(lines)
        except Exception:
            return f"[search_sop 异常] 知识库检索不可用: {e}"
