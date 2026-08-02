"""初始化企业业务数据 — 运行一次即可"""
from database.mysql import SessionLocal
from db_models.business import Employee, Ticket, LeaveRecord

employees_data = [
    {"name":"张三","dept":"HR","role":"实习生","status":"在职","hire_date":"2025-06-01","phone":"1380000101","email":"zhangsan@company.com"},
    {"name":"李四","dept":"TECH","role":"实习生","status":"在职","hire_date":"2025-06-15","phone":"1380000102","email":"lisi@company.com"},
    {"name":"王建国","dept":"ADMIN","role":"CEO","status":"在职","hire_date":"2018-01-01","phone":"1380000103","email":"wangjianguo@company.com"},
    {"name":"赵伟","dept":"TECH","role":"技术总监","status":"在职","hire_date":"2019-03-15","phone":"1380000104","email":"zhaowei@company.com"},
    {"name":"张丽华","dept":"HR","role":"HR经理","status":"在职","hire_date":"2020-06-01","phone":"1380000105","email":"zhanglihua@company.com"},
    {"name":"马超","dept":"TECH","role":"运维工程师","status":"在职","hire_date":"2021-01-15","phone":"1380000106","email":"machao@company.com"},
    {"name":"孙涛","dept":"TECH","role":"后端开发组长","status":"在职","hire_date":"2020-09-01","phone":"1380000107","email":"suntao@company.com"},
    {"name":"刘洋","dept":"HR","role":"培训专员","status":"在职","hire_date":"2022-07-01","phone":"1380000108","email":"liuyang@company.com"},
]

tickets_data = [
    {"ticket_no":"TKT-001","title":"user-service 500错误","status":"已解决","priority":"P0","assignee":"马超","created":"2026-07-27 10:06","resolved":"2026-07-27 10:45","solution":"重启服务+扩大连接池至50"},
    {"ticket_no":"TKT-002","title":"payment-service Redis超时","status":"已解决","priority":"P1","assignee":"孙涛","created":"2026-07-27 10:06","resolved":"2026-07-27 10:20","solution":"切换DB队列降级,重启Redis恢复"},
    {"ticket_no":"TKT-003","title":"VPN无法连接","status":"处理中","priority":"P2","assignee":"马超","created":"2026-07-28 09:15","resolved":None,"solution":None},
    {"ticket_no":"TKT-004","title":"订单服务响应慢","status":"已解决","priority":"P1","assignee":"孙涛","created":"2026-07-25 14:00","resolved":"2026-07-25 17:30","solution":"优化慢SQL,添加复合索引"},
    {"ticket_no":"TKT-005","title":"OA系统登录异常","status":"已解决","priority":"P2","assignee":"马超","created":"2026-07-26 08:30","resolved":"2026-07-26 09:00","solution":"SSO证书过期,更新证书"},
]

leave_data = [
    {"name":"张三","dept":"HR","type":"年假","start_date":"2026-08-01","end_date":"2026-08-01","days":1,"status":"待审批","approver":"张丽华"},
    {"name":"张三","dept":"HR","type":"病假","start_date":"2026-06-15","end_date":"2026-06-15","days":1,"status":"已通过","approver":"张丽华"},
    {"name":"李四","dept":"TECH","type":"年假","start_date":"2026-08-05","end_date":"2026-08-07","days":3,"status":"待审批","approver":"赵伟"},
    {"name":"马超","dept":"TECH","type":"事假","start_date":"2026-07-28","end_date":"2026-07-28","days":1,"status":"已通过","approver":"赵伟"},
    {"name":"刘洋","dept":"HR","type":"年假","start_date":"2026-08-10","end_date":"2026-08-14","days":5,"status":"已通过","approver":"张丽华"},
]


def seed():
    db = SessionLocal()
    try:
        # 清空已有数据
        db.query(LeaveRecord).delete()
        db.query(Ticket).delete()
        db.query(Employee).delete()

        for d in employees_data:
            db.add(Employee(**d))
        for d in tickets_data:
            db.add(Ticket(**d))
        for d in leave_data:
            db.add(LeaveRecord(**d))

        db.commit()
        print(f"已插入: {len(employees_data)} 员工, {len(tickets_data)} 工单, {len(leave_data)} 请假记录")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
