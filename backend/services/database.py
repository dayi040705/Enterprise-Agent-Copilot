"""
企业数据查询层 — MySQL OLTP + analytics OLAP

架构:
  MySQL (enterprise_rag 库): orders/products/reviews — 实时交易数据
  analytics 库:              sales_daily/listing_snapshots — 预聚合趋势数据

面试金句:
  "Agent 查当前订单状态走 query_mysql → enterprise_rag 库 (OLTP)。
   查销量趋势走 query_analytics → analytics 库 (OLAP)。
   同一个 Agent 根据问题类型自动选择数据源。"
"""
from database.mysql import SessionLocal
from sqlalchemy import text
import json


# ============================================================
# OLTP 查询 — 电商实时交易表
# ============================================================

E_COMMERCE_TABLES = {
    "products": {
        "desc": "商品/Listing 表",
        "columns": "product_id, category, product_name, brand, price, cost",
        "example": "SELECT category, AVG(price) FROM products GROUP BY category",
    },
    "orders": {
        "desc": "订单表",
        "columns": "order_id, customer_id, order_status, purchase_date, delivered_date",
        "example": "SELECT order_status, COUNT(*) FROM orders WHERE purchase_date > '2026-08-01' GROUP BY order_status",
    },
    "order_items": {
        "desc": "订单明细表",
        "columns": "order_id, product_id, seller_id, price, freight, discount_rate",
        "example": "SELECT product_id, SUM(price) FROM order_items WHERE order_id IN (SELECT order_id FROM orders WHERE purchase_date > '2026-08-01') GROUP BY product_id",
    },
    "order_reviews": {
        "desc": "订单评价表",
        "columns": "review_id, order_id, score, comment_title, comment, creation_date",
        "example": "SELECT score, COUNT(*) FROM order_reviews GROUP BY score",
    },
    "sellers": {
        "desc": "卖家表",
        "columns": "seller_id, company_name, contact_name, city, state",
        "example": "SELECT city, COUNT(*) FROM sellers GROUP BY city",
    },
    "order_payments": {
        "desc": "支付记录表",
        "columns": "order_id, payment_type, installments, amount",
        "example": "SELECT payment_type, COUNT(*), SUM(amount) FROM order_payments GROUP BY payment_type",
    },
    "sync_logs": {
        "desc": "数据管道同步日志 (SP-API 数据录入监控)",
        "columns": "batch_id, source, table_name, total, success, failed, error_detail, sync_time",
        "example": "SELECT source, table_name, total, success, failed, ROUND(success/total*100,1) as ingest_rate FROM sync_logs WHERE sync_time > '2026-08-06' ORDER BY sync_time DESC",
    },
}


def _query_oltp(sql: str) -> str:
    """执行 OLTP SQL 查询 (enterprise_rag 库)"""
    db = SessionLocal()
    try:
        result = db.execute(text(sql))
        rows = result.fetchall()
        if not rows:
            return "[OLTP] 查询无结果。请检查条件是否正确。"

        cols = result.keys()
        lines = [f"[OLTP] 共 {len(rows)} 条"]
        for row in rows[:15]:
            line = " | ".join(f"{c}={v}" for c, v in zip(cols, row) if v is not None)
            lines.append(line[:500])
        return "\n".join(lines)
    except Exception as e:
        return f"[OLTP 查询异常] {e}\n可用表: {', '.join(E_COMMERCE_TABLES.keys())}"
    finally:
        db.close()


def get_oltp_schema() -> str:
    """返回 OLTP 表结构 (供 Agent 参考)"""
    lines = ["## MySQL OLTP 表 (查实时订单/商品/评价):"]
    for table, info in E_COMMERCE_TABLES.items():
        lines.append(f"\n### {table} — {info['desc']}")
        lines.append(f"列: {info['columns']}")
        lines.append(f"示例: {info['example']}")
    return "\n".join(lines)


# ============================================================
# OLAP 查询 — analytics 预聚合趋势表
# ============================================================

ANALYTICS_TABLES = {
    "sales_daily": {
        "desc": "日销量汇总 (每天凌晨 ETL 从 orders+items 聚合)",
        "columns": "date, sku, units_sold, revenue, refund_units, refund_rate, avg_price",
        "note": "查销量趋势/退款率对比/均价变化 — 不要查 orders 表 JOIN! 直接查这张表",
        "example": "SELECT date, SUM(units_sold), SUM(revenue) FROM analytics.sales_daily WHERE date > '2026-07-01' GROUP BY date ORDER BY date",
    },
    "listing_snapshots": {
        "desc": "Listing 每日评分/排名快照 (ETL 聚合)",
        "columns": "date, sku, category, avg_rating, total_reviews, active_orders, total_revenue",
        "example": "SELECT sku, avg_rating, total_reviews FROM analytics.listing_snapshots WHERE date='2026-08-06' ORDER BY avg_rating DESC LIMIT 10",
    },
    "sync_etl_log": {
        "desc": "数据管道 ETL 同步监控日志 (当天数据录入/延迟/失败)",
        "columns": "batch_time, source, table_name, rows_synced, latency_sec",
        "example": "SELECT * FROM analytics.sync_etl_log WHERE batch_time > now() - INTERVAL 1 DAY ORDER BY batch_time DESC",
    },
}


def _query_olap(sql: str) -> str:
    """执行 OLAP SQL 查询 (analytics 库)"""
    db = SessionLocal()
    try:
        # 自动加 analytics. 前缀
        for table in ANALYTICS_TABLES:
            if table in sql and f"analytics.{table}" not in sql:
                sql = sql.replace(table, f"analytics.{table}")

        result = db.execute(text(sql))
        rows = result.fetchall()
        if not rows:
            return "[OLAP] 查询无结果。analytics 库的数据由每天凌晨 ETL 预聚合生成。"

        cols = result.keys()
        lines = [f"[OLAP] 共 {len(rows)} 条 (预聚合数据, 毫秒级查询)"]
        for row in rows[:15]:
            line = " | ".join(f"{c}={v}" for c, v in zip(cols, row) if v is not None)
            lines.append(line[:500])
        return "\n".join(lines)
    except Exception as e:
        return f"[OLAP 查询异常] {e}\n可用表: sales_daily / listing_snapshots / sync_etl_log"
    finally:
        db.close()


def get_olap_schema() -> str:
    """返回 OLAP 表结构 (供 Agent 参考)"""
    lines = ["## analytics OLAP 表 (查趋势/聚合/监控, 预计算数据, 毫秒级):"]
    for table, info in ANALYTICS_TABLES.items():
        lines.append(f"\n### {table} — {info['desc']}")
        lines.append(f"列: {info['columns']}")
        if "note" in info:
            lines.append(f"⚠️ {info['note']}")
        lines.append(f"示例: {info['example']}")
    return "\n".join(lines)
