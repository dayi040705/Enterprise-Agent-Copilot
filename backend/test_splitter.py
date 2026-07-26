"""对比三种分块策略的效果"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from services.splitter import compare_strategies

text = "第一条 为规范公司考勤管理，保障员工合法权益，根据国家相关法律法规，结合公司实际情况，制定本制度。\n第二条 本制度适用于公司全体在职员工。\n第三条 人力资源部是考勤管理的归口部门，负责员工请假的审批、审核及系统维护工作。\n第二章 假期种类及标准\n第四条 法定节假日：员工享有国家规定的法定节假日，包括元旦、春节、清明节、劳动节、端午节、中秋节、国庆节。具体放假安排以国务院办公厅发布的年度通知为准。\n第五条 年休假：员工累计工作已满1年不满10年的，年休假5天；已满10年不满20年的，年休假10天；已满20年的，年休假15天。国家法定休假日、休息日不计入年休假的假期。\n第六条 病假：员工因病或非因工负伤需要治疗的，凭医院出具的病休证明，可以申请病假。"

print("原文长度:", len(text), "字")
print("=" * 70)

results = compare_strategies(text)
for strategy, info in results.items():
    print()
    print(f"[{strategy}]  {info['count']:2d} 个块, 平均 {info['avg_size']:3d} 字")
    print(f"  首块: {info['sample']}")
