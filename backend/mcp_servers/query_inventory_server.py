"""
MCP Server: query_inventory
查库存/安全库存预警 — 基于 analytics.sales_daily 日销量反推库存健康度

生产环境: 对接真实 WMS/ERP 库存系统
当前: analytics.sales_daily + 库存管理规范 SOP
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.mysql import SessionLocal
from sqlalchemy import text


def query_low_stock(min_days: int = 30, limit: int = 10) -> str:
    """查库存预警 — 最近 30 天销量 > 0 但最近 7 天无销售的 SKU (可能断货)

    参数:
      min_days: 预警天数阈值, 默认 30
      limit:    返回条数
    """
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT sku,
                   SUM(CASE WHEN date > DATE_SUB(NOW(), INTERVAL 7 DAY) THEN units_sold ELSE 0 END) as recent_sales,
                   SUM(CASE WHEN date > DATE_SUB(NOW(), INTERVAL 30 DAY) THEN units_sold ELSE 0 END) as month_sales,
                   AVG(refund_rate) as avg_refund
            FROM analytics.sales_daily
            GROUP BY sku
            HAVING month_sales > 5 AND recent_sales = 0
            ORDER BY month_sales DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()

        if not rows:
            return "[query_inventory] 所有活跃 SKU 近 7 天均有销售, 库存健康"

        lines = [f"[query_inventory | MCP] 库存预警 Top {len(rows)} (近7天无销售但30天内有销量):"]
        for sk, recent, month, refund in rows:
            lines.append(f"  {sk[:25]}... | 近30天售{month}件 | 近7天:{recent}件 ⚠️ | 退款率{refund:.1f}%")
        return "\n".join(lines)
    except Exception as e:
        return f"[query_inventory 异常] {e}"
    finally:
        db.close()
