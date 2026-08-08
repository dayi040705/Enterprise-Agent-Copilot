"""初始化电商业务数据 — MySQL (OLTP) + ClickHouse (OLAP)"""
from database.mysql import SessionLocal
from db_models.business import Employee, Ticket, LeaveRecord

# ============================================================
# MySQL 数据 — OLTP: 订单/库存/工单 (实时读写, 查当前状态)
# ============================================================

# 改成电商场景: 员工表 → 运营团队
employees_data = [
    {"name":"陈运营","dept":"运营","role":"运营主管","status":"在职","hire_date":"2024-03-01","phone":"1380000301","email":"chenyy@company.com"},
    {"name":"李广告","dept":"运营","role":"广告优化师","status":"在职","hire_date":"2024-06-15","phone":"1380000302","email":"ligg@company.com"},
    {"name":"王客服","dept":"客服","role":"客服经理","status":"在职","hire_date":"2023-09-01","phone":"1380000303","email":"wangkf@company.com"},
    {"name":"赵库存","dept":"供应链","role":"库存管理","status":"在职","hire_date":"2024-01-15","phone":"1380000304","email":"zhaokc@company.com"},
    {"name":"孙开发","dept":"技术","role":"后端开发","status":"在职","hire_date":"2025-06-01","phone":"1380000305","email":"sunkf@company.com"},
    {"name":"钱数据","dept":"数据","role":"数据分析师","status":"在职","hire_date":"2025-03-01","phone":"1380000306","email":"qiansj@company.com"},
    {"name":"周选品","dept":"产品","role":"选品经理","status":"在职","hire_date":"2024-08-01","phone":"1380000307","email":"zhouxp@company.com"},
    {"name":"吴物流","dept":"供应链","role":"物流专员","status":"在职","hire_date":"2025-01-01","phone":"1380000308","email":"wuwl@company.com"},
]

# 电商售后工单
tickets_data = [
    {"ticket_no":"CS-001","title":"订单 #2401-087 买家反馈收到破损商品","status":"处理中","priority":"P1","assignee":"王客服","created":"2026-08-06 09:15","resolved":None,"solution":None},
    {"ticket_no":"CS-002","title":"Listing B07XXX 转化率一周内从 8% 跌到 2.1%","status":"已解决","priority":"P0","assignee":"陈运营","created":"2026-08-04 10:00","resolved":"2026-08-04 14:30","solution":"发现被跟卖 + 新差评,发起品牌备案投诉,联系买家删评"},
    {"ticket_no":"CS-003","title":"SKU X9A-001 库存只有 23 件低于安全库存(50件)","status":"处理中","priority":"P0","assignee":"赵库存","created":"2026-08-06 08:00","resolved":None,"solution":None},
    {"ticket_no":"CS-004","title":"订单 #2408-123 支付成功但未同步到 ERP","status":"已解决","priority":"P1","assignee":"孙开发","created":"2026-08-05 16:20","resolved":"2026-08-05 17:45","solution":"Amazon SP-API 限流,换备用 token 后重试成功"},
    {"ticket_no":"CS-005","title":"广告组 AG-005 昨天花费翻倍但订单量没涨","status":"处理中","priority":"P2","assignee":"李广告","created":"2026-08-06 07:30","resolved":None,"solution":None},
    {"ticket_no":"CS-006","title":"Listing B08AAA 突然被平台下架","status":"已解决","priority":"P0","assignee":"陈运营","created":"2026-08-03 11:00","resolved":"2026-08-03 13:00","solution":"侵权投诉导致,提交品牌授权书后 2 小时恢复"},
    {"ticket_no":"CS-007","title":"物流显示已签收但买家说没收到","status":"处理中","priority":"P1","assignee":"吴物流","created":"2026-08-06 10:00","resolved":None,"solution":None},
    {"ticket_no":"CS-008","title":"黑五备货计划: SKU B10-X 需要预估订单量","status":"已解决","priority":"P1","assignee":"钱数据","created":"2026-08-03 14:00","resolved":"2026-08-03 16:00","solution":"ClickHouse 拉取近6个月月销趋势曲线,安全库存从50提到400"},
]

# ============================================================
# ClickHouse 数据 — OLAP: 广告/排名/销量 (只写不删, 聚合分析)
# ============================================================

# ClickHouse 表结构 (注释, 实际部署时执行):
# CREATE TABLE ad_performance (
#     date Date, sku String, campaign_id String,
#     impressions UInt32, clicks UInt32, spend Decimal(10,2),
#     orders UInt32, sales Decimal(10,2)
# ) ENGINE = MergeTree() ORDER BY (date, sku);

# CREATE TABLE listing_rankings (
#     date Date, sku String, keyword String,
#     organic_rank UInt16, ad_rank UInt16,
#     rating Decimal(2,1), review_count UInt16
# ) ENGINE = MergeTree() ORDER BY (date, sku);

# CREATE TABLE sales_daily (
#     date Date, sku String,
#     units_sold UInt32, revenue Decimal(10,2),
#     refund_units UInt16, refund_rate Decimal(4,2)
# ) ENGINE = SummingMergeTree() ORDER BY (date, sku);

# 示例数据 (模拟过去 7 天的广告和销量数据)
# 面试可以直接说:
# "MySQL 存订单和库存, ClickHouse 存几亿条广告曝光和销量历史。
#  Agent 调 Action Agent 时先查 MySQL 看当前状态,
#  再查 ClickHouse 看趋势, 然后综合诊断。"


def seed():
    db = SessionLocal()
    try:
        # 清空已有数据
        db.query(LeaveRecord).delete()
        db.query(Ticket).delete()
        db.query(Employee).delete()

        for e in employees_data:
            db.add(Employee(**e))
        for t in tickets_data:
            db.add(Ticket(**t))

        db.commit()
        print(f"种子完成: {len(employees_data)} 电商运营员工, {len(tickets_data)} 条售后工单")

        print("\nMySQL 角色: 订单表(orders)/库存表(inventory)/工单表(tickets) → OLTP 实时查询")
        print("ClickHouse 角色: 广告效果/Listing排名/日销量趋势 → OLAP 聚合分析")
        print("Agent 查数据时先 MySQL 看现状,再 ClickHouse 看趋势,综合诊断")

    except Exception as e:
        db.rollback()
        print(f"种子失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
