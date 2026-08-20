"""
双引擎性能对比演示 — 面试彩蛋用

用法 (backend 目录下):
    python scripts/benchmark_dual_engine.py

演示 MySQL OLTP 三表 JOIN vs analytics 预聚合表的速度差距。
输出为 UTF-8, 在 Windows 终端乱码时先执行: chcp 65001
"""
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, sys.path[0])

import pymysql

DB = dict(host='localhost', user='root', password='123456',
          database='enterprise_rag', charset='utf8mb4')


def line(char='─', width=72):
    print(char * width)


def main():
    conn = pymysql.connect(**DB)
    cur = conn.cursor()

    print()
    print('=' * 72)
    print('  双引擎数据架构性能对比 (MySQL OLTP vs analytics 预聚合)')
    print('=' * 72)

    # ── 1. 数据量 ──
    print()
    print('【数据量】')
    total = 0
    for t in ['orders', 'order_items', 'order_reviews', 'products', 'sellers', 'order_payments']:
        cur.execute(f'SELECT COUNT(*) FROM {t}')
        n = cur.fetchone()[0]
        total += n
        print(f'  MySQL.{t:<18} {n:>10,} 行')
    print(f'  {"合计":<26} {total:>10,} 行 (≈137万)')
    cur.execute('SELECT COUNT(*) FROM analytics.sales_daily')
    n = cur.fetchone()[0]
    print(f'  analytics.sales_daily     {n:>10,} 行 (预聚合日销量)')

    # ── 2. 慢查询: 三表 JOIN ──
    slow_sql = """
        SELECT oi.product_id AS sku,
               COUNT(*) AS total_items,
               AVG(rv.score) AS avg_score
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN order_reviews rv ON o.order_id = rv.order_id
        GROUP BY oi.product_id
        ORDER BY total_items DESC LIMIT 5
    """
    print()
    print('【慢查询】MySQL 三表 JOIN 聚合 (orders + order_items + order_reviews)')
    print('  执行中, 请观察耗时...')
    t0 = time.time()
    cur.execute(slow_sql)
    rows = cur.fetchall()
    slow = time.time() - t0
    print(f'  → 耗时: {slow:.1f} 秒')
    for r in rows[:3]:
        print(f'    SKU {r[0][:12]}... | {r[1]} 条 | 均分 {r[2]:.2f}')

    # ── 3. 快查询: 预聚合点查 ──
    sku = rows[0][0]
    fast_sql = f"""
        SELECT date, units_sold, revenue, refund_rate
        FROM analytics.sales_daily
        WHERE sku = '{sku}' AND units_sold > 0
        ORDER BY date DESC LIMIT 10
    """
    print()
    print('【快查询】analytics.sales_daily 预聚合点查 (同一 SKU)')
    t0 = time.time()
    cur.execute(fast_sql)
    rows2 = cur.fetchall()
    fast = time.time() - t0
    print(f'  → 耗时: {fast:.4f} 秒')
    for r in rows2[:3]:
        print(f'    {r[0]} | 售 {r[1]} 件 | 收入 {r[2]:.0f} | 退款率 {r[3]:.1f}%')

    # ── 4. 对比 ──
    print()
    line('═')
    print(f'  性能差距: {slow:.1f}s / {fast:.4f}s ≈ {slow / fast:,.0f} 倍')
    print(f'  (三表 JOIN 扫描 93 万评价行 vs 预聚合表单 SKU 索引点查)')
    line('═')
    print()
    print('  架构逻辑: 每天凌晨 ETL 把 orders+items 聚合进 sales_daily')
    print('  Agent 查趋势/排行走 analytics (毫秒级), 查实时订单状态走 MySQL')
    print('  ClickHouse OLAP schema 见 schemas/clickhouse_schema.sql (扩展方案)')
    print()
    conn.close()


if __name__ == '__main__':
    main()
