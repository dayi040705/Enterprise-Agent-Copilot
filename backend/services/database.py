"""
企业数据库查询 — Agent query_database 的底层实现

MySQL 表: employees / tickets / leave_records
"""
from database.mysql import SessionLocal
from db_models.business import Employee, Ticket, LeaveRecord

TABLE_MAP = {
    "employees": Employee,
    "tickets": Ticket,
    "leave_records": LeaveRecord,
}


def query_table(table: str, filters: dict) -> dict:
    """查询 MySQL 业务表, 返回 {table, columns, rows, total}"""
    model = TABLE_MAP.get(table)
    if not model:
        return {"table": table, "columns": [], "rows": [], "total": 0,
                "error": f"表 {table} 不存在。可用: employees / tickets / leave_records"}

    db = SessionLocal()
    try:
        q = db.query(model)

        # 按条件过滤 — 对应字段模糊匹配
        field_map = {
            "name": ["name"],
            "dept": ["dept"],
            "status": ["status"],
            "title": ["title"],
            "assignee": ["assignee"],
        }

        for key, value in filters.items():
            if value and key in field_map:
                for col_name in field_map[key]:
                    col = getattr(model, col_name, None)
                    if col:
                        q = q.filter(col.like(f"%{value}%"))

        rows = q.limit(20).all()

        # 转成 dict 列表
        cols = [c.name for c in model.__table__.columns]
        data = []
        for r in rows:
            data.append({c: str(getattr(r, c)) if getattr(r, c) is not None else ""
                         for c in cols})

        return {"table": table, "columns": cols, "rows": data, "total": len(data),
                "filters_applied": filters}
    finally:
        db.close()
