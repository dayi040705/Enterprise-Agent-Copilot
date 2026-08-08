"""
MCP Server: query_analytics
查销量趋势/退款率/Listing排名 (OLAP预聚合,毫秒级)
数据源: analytics.sales_daily (每天凌晨 ETL 从 orders+items 聚合)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.mysql import SessionLocal
from sqlalchemy import text


def query_sales_trend(sku: str = "", date_from: str = "", limit: int = 10) -> str:
    """查日销量趋势/退款率/均价 — 预聚合数据, 毫秒级"""
    db = SessionLocal()
    try:
        conditions = ["1=1"]
        if sku: conditions.append(f"sku = '{sku}'")
        if date_from: conditions.append(f"date > '{date_from}'")
        where = " AND ".join(conditions)

        rows = db.execute(text(f"""
            SELECT date, sku, units_sold, revenue, refund_rate, avg_price
            FROM analytics.sales_daily WHERE {where}
            ORDER BY date DESC, units_sold DESC LIMIT {limit}
        """)).fetchall()

        if not rows:
            return "[query_analytics] analytics.sales_daily 未找到匹配记录"

        lines = [f"[query_analytics | MCP] 销量趋势 (预聚合, {len(rows)} 条)"]
        for dt, sk, sold, rev, ref_rate, avg_p in rows:
            lines.append(f"  {dt} | {sk[:20]}... | 售{sold}件 | ¥{rev or 0:.0f} | 退款率{ref_rate or 0:.1f}%")
        return "\n".join(lines)
    except Exception as e:
        return f"[query_analytics 异常] {e}"
    finally:
        db.close()


def query_top_refund_skus(date_from: str = "", limit: int = 5) -> str:
    """查退款率最高的 Top N SKU — 异常诊断"""
    db = SessionLocal()
    try:
        cond = f"WHERE date > '{date_from}'" if date_from else ""
        rows = db.execute(text(f"""
            SELECT sku, SUM(units_sold) as total_sold, AVG(refund_rate) as avg_rr
            FROM analytics.sales_daily {cond}
            GROUP BY sku HAVING total_sold > 10
            ORDER BY avg_rr DESC LIMIT {limit}
        """)).fetchall()

        if not rows:
            return "[query_analytics] 未找到匹配的退款数据"

        lines = [f"[query_analytics | MCP] 退款率 Top {len(rows)} (销量>10件):"]
        for sk, sold, rr in rows:
            lines.append(f"  {sk[:30]}... | 售{sold}件 | 退款率{rr:.1f}%")
        return "\n".join(lines)
    except Exception as e:
        return f"[query_analytics 异常] {e}"
    finally:
        db.close()
