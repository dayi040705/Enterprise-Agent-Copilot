"""
MCP Server: query_sync_logs
查数据管道同步日志/录入率/延迟 — 监控 SP-API → MySQL 数据健康度
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.mysql import SessionLocal
from sqlalchemy import text


def query_sync_health(hours: int = 24) -> str:
    """查最近 N 小时数据管道健康度: 每批次的录入率/失败原因

    参数:
      hours: 查最近多少小时, 默认 24
    """
    db = SessionLocal()
    try:
        rows = db.execute(text(f"""
            SELECT sync_time, source, table_name, total, COALESCE(success,0), COALESCE(failed,0),
                   ROUND(COALESCE(success,0)/NULLIF(total,0)*100, 1) as rate, COALESCE(error_detail,'')
            FROM sync_logs
            ORDER BY sync_time DESC
            LIMIT 20
        """)).fetchall()

        if not rows:
            return f"[query_sync_logs] 最近 {hours} 小时内无同步记录"

        total_ok = sum((r[4] or 0) for r in rows)
        total_all = sum((r[3] or 0) for r in rows)
        overall_rate = round(total_ok / total_all * 100, 1) if total_all else 0

        lines = [
            f"[query_sync_logs | MCP] 最近 {hours}h 数据管道健康度",
            f"综合录入率: {overall_rate}% ({total_ok}/{total_all})",
            f"共 {len(rows)} 批次:",
        ]
        for st, src, tbl, total, ok, fail, rate, err in rows:
            rate_val = rate or 0  # NULL → 0
            status = "[OK]" if rate_val >= 99 else "[WARN]" if rate_val >= 95 else "[FAIL]"
            err_info = f" — {err[:50]}" if err else ""
            lines.append(f"  {status} {str(st)[:16]} | {src} → {tbl}: {ok}/{total} ({rate_val}%){err_info}")
        return "\n".join(lines)
    except Exception as e:
        return f"[query_sync_logs 异常] {e}"
    finally:
        db.close()
