"""
MCP Server: query_orders
查订单状态/退款/异常 (OLTP实时数据)
独立部署, 可被 Agent 通过 MCP Client 远程调用
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.mysql import SessionLocal
from sqlalchemy import text


def query_orders(order_id: str = "", status: str = "", date_from: str = "", limit: int = 10) -> str:
    """查订单状态/退款/异常"""
    db = SessionLocal()
    try:
        conditions = ["1=1"]
        if order_id: conditions.append(f"order_id = '{order_id}'")
        if status:   conditions.append(f"order_status = '{status}'")
        if date_from: conditions.append(f"purchase_date > '{date_from}'")
        where = " AND ".join(conditions)

        rows = db.execute(text(f"""
            SELECT order_id, order_status, purchase_date, delivered_date
            FROM orders WHERE {where}
            ORDER BY purchase_date DESC LIMIT {limit}
        """)).fetchall()

        if not rows:
            return f"[query_orders] 未找到匹配订单 (status: {status or '全部'}, date_from: {date_from or '不限'})"

        lines = [f"[query_orders | MCP] 共 {len(rows)} 条"]
        for oid, st, pd, dl in rows:
            lines.append(f"  {oid[:24]}... | {st} | {pd} | 签收:{dl or '未签收'}")
        return "\n".join(lines)
    except Exception as e:
        return f"[query_orders 异常] {e}"
    finally:
        db.close()
