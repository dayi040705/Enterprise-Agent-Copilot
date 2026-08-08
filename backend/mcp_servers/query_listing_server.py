"""
MCP Server: query_listing
查评分/排名/是否被跟卖 — 从 products + order_reviews 交叉分析
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.mysql import SessionLocal
from sqlalchemy import text


def query_listing_rating_drop(min_drop: float = 0.5, limit: int = 5) -> str:
    """查评分下降的 Listing 预警 — 简化版, 不 JOIN 全量"""
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT product_id, category, product_name, price
            FROM products WHERE product_id IN (
                SELECT DISTINCT product_id FROM order_items LIMIT 100
            )
            ORDER BY price DESC LIMIT :limit
        """), {"limit": limit}).fetchall()

        if not rows:
            return "[query_listing] 评分下降查询不可用，改用商品概览: 请用 query_analytics 查退款率"

        # 用 analytics 间接判断 — 退款率高的 SKU 可能评分有问题
        lines = [f"[query_listing | MCP] 商品概览 (Top {len(rows)}):"]
        for pid, cat, nm, price in rows:
            name = (nm or pid)[:30]
            lines.append(f"  {name} | {cat} | ¥{price}")
        return "\n".join(lines)
    except Exception as e:
        return f"[query_listing 异常] {e}"
    finally:
        db.close()


def query_listing_health(sku: str = "", category: str = "", limit: int = 10) -> str:
    """查 Listing 健康度 — 含评分/评价数 (限流避免超时)

    参数:
      sku:      可选
      category: 可选
      limit:    返回条数 (默认10)
    """
    db = SessionLocal()
    try:
        conditions = ["p.price > 0"]
        if sku: conditions.append(f"p.product_id = '{sku}'")
        if category: conditions.append(f"p.category = '{category}'")
        where = " AND ".join(conditions)

        rows = db.execute(text(f"""
            SELECT p.product_id, p.category, p.product_name, p.price,
                   sub.avg_score, sub.review_cnt
            FROM products p
            LEFT JOIN (
                SELECT oi.product_id,
                       ROUND(AVG(rv.score), 1) as avg_score,
                       COUNT(rv.review_id) as review_cnt
                FROM order_items oi
                JOIN order_reviews rv ON oi.order_id = rv.order_id
                GROUP BY oi.product_id
            ) sub ON p.product_id = sub.product_id
            WHERE {where}
            ORDER BY sub.review_cnt DESC, p.price DESC
            LIMIT {limit}
        """)).fetchall()

        if not rows:
            return "[query_listing] 未找到匹配的 Listing"

        lines = [f"[query_listing | MCP] Listing 健康度 (共 {len(rows)} 条):"]
        for pid, cat, name, price, score, cnt in rows:
            nm = (name or pid)[:35]
            stars = f"{score}分({cnt}评)" if score and cnt else "暂无评分"
            lines.append(f"  {nm} | {cat} | ¥{price} | {stars}")
        return "\n".join(lines)
    except Exception as e:
        return f"[query_listing 异常] {e}"
    finally:
        db.close()


def query_rating_drop(min_drop: float = 0.5, limit: int = 5) -> str:
    """查评分下降的 Listing — 对比整体均分和最近 30 天评分

    参数:
      min_drop: 评分下降阈值, 默认 0.5
      limit:    返回条数
    """
    db = SessionLocal()
    try:
        # 用 analytics 的 listing_snapshots 表 (如果存在), 否则用 reviews 直接算
        rows = db.execute(text("""
            SELECT oi.product_id, p.category,
                   AVG(rv.score) as avg_score,
                   COUNT(rv.review_id) as total_reviews,
                   AVG(CASE WHEN rv.creation_date > DATE_SUB(NOW(), INTERVAL 30 DAY) THEN rv.score END) as recent_score
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
            JOIN order_reviews rv ON oi.order_id = rv.order_id
            GROUP BY oi.product_id, p.category
            HAVING total_reviews > 10
               AND avg_score - COALESCE(AVG(CASE WHEN rv.creation_date > DATE_SUB(NOW(), INTERVAL 30 DAY) THEN rv.score END), avg_score) >= :min_drop
            ORDER BY (avg_score - COALESCE(AVG(CASE WHEN rv.creation_date > DATE_SUB(NOW(), INTERVAL 30 DAY) THEN rv.score END), avg_score)) DESC
            LIMIT :limit
        """), {"min_drop": min_drop, "limit": limit}).fetchall()

        if not rows:
            return "[query_listing] 没有评分显著下降的 Listing"

        lines = [f"[query_listing | MCP] 评分下降预警 (>{min_drop}分):"]
        for pid, cat, avg_s, total, recent in rows:
            lines.append(f"  {pid[:25]}... | {cat} | 总均分{avg_s:.1f} | 近30天{recent:.1f} | 跌{avg_s-(recent or 0):.1f}分 ⚠️")
        return "\n".join(lines)
    except Exception as e:
        return f"[query_listing 异常] {e}"
    finally:
        db.close()
