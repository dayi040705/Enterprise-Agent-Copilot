"""生成电商服务日志 — 基于真实订单数据"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.mysql import engine
from sqlalchemy import text
import random
random.seed(42)

with engine.connect() as conn:
    items = conn.execute(text('SELECT DISTINCT product_id FROM order_items LIMIT 30')).fetchall()
    skus = [r[0][:12] for r in items]
    orders = conn.execute(text("SELECT order_id FROM orders WHERE order_status='canceled' LIMIT 20")).fetchall()
    canceled = [r[0][:12] for r in orders]

lines = []

# sp-api.log — 数据管道同步日志, 和 sync_logs 表对应
sync_events = [
    ('08-06 00:15', 'INFO', 'SyncManager', 'Starting scheduled sync: orders, order_items, inventory'),
    ('08-06 00:15', 'INFO', 'OrderSync', 'Fetched 520 orders from SP-API (Orders API v2)'),
    ('08-06 00:15', 'INFO', 'OrderSync', 'Orders written to MySQL: 520/520 succeeded'),
    ('08-06 00:15', 'INFO', 'ItemSync', 'Fetched 1510 items from SP-API'),
    ('08-06 00:15', 'WARN', 'ItemSync', '2 items failed FK constraint: order not found in local DB'),
    ('08-06 00:15', 'INFO', 'ItemSync', 'Items written to MySQL: 1508/1510 succeeded'),
    ('08-06 01:00', 'INFO', 'InventorySync', 'Fetched 200 SKU inventory levels'),
    ('08-06 01:00', 'WARN', 'InventorySync', '5 SKUs skipped: mapping not found in product catalog'),
    ('08-06 08:15', 'INFO', 'OrderSync', 'Fetched 480 orders from SP-API'),
    ('08-06 08:15', 'WARN', 'OrderSync', '5 orders failed JSON parsing: unexpected field format change'),
    ('08-06 08:15', 'ERROR', 'OrderSync', 'JSON parse error at order: unknown field seller_feedback_v2'),
    ('08-06 12:30', 'WARN', 'RateLimiter', 'SP-API returning 429 Too Many Requests. Retry-After: 60s'),
    ('08-06 12:30', 'ERROR', 'OrderSync', 'Rate limit hit: only fetched 280/350 orders. 70 orders deferred.'),
    ('08-06 12:30', 'WARN', 'ItemSync', 'Rate limit hit: only fetched 780/980 items. 200 items deferred.'),
    ('08-06 12:35', 'CRITICAL', 'AuthManager', 'SP-API token refresh failed: invalid_grant - client secret expired'),
    ('08-06 12:35', 'CRITICAL', 'SyncManager', 'All sync tasks ABORTED. Total lost: 350 orders, 980 items.'),
    ('08-06 12:35', 'INFO', 'AlertManager', 'P0 alert: SP-API sync down due to auth failure'),
    ('08-06 13:00', 'INFO', 'AuthManager', 'New client secret configured. Token refresh successful.'),
    ('08-06 13:00', 'INFO', 'SyncManager', 'Recovery sync: backfill 12:30-12:55 window'),
    ('08-06 13:00', 'INFO', 'OrderSync', 'Backfill: 420 orders recovered'),
    ('08-07 00:15', 'INFO', 'OrderSync', 'Normal sync: 510 orders, all succeeded'),
    ('08-07 12:30', 'WARN', 'InventorySync', '20/200 SKUs skipped: Listing already deleted on Amazon'),
    ('08-08 00:15', 'INFO', 'SyncManager', 'Normal sync completed. 24h avg ingestion rate: 97.3 percent'),
]
for ts, level, comp, msg in sync_events:
    lines.append(('sp-api.log', f'2026-{ts} [{level}] [{comp}] {msg}'))

# order-service.log — 关联真实取消订单
for i, oid in enumerate(canceled[:10]):
    h, m, s = random.randint(8, 22), random.randint(0, 59), random.randint(0, 59)
    lines.append(('order-service.log', f'2026-08-06 {h:02d}:{m:02d}:{s:02d} [WARN] [OrderProcessor] Order {oid} payment timeout: gateway no response in 30s'))
    lines.append(('order-service.log', f'2026-08-06 {h:02d}:{m+1:02d}:{s:02d} [INFO] [OrderProcessor] Order {oid} status -> canceled, refund initiated'))

lines.append(('order-service.log', '2026-08-06 12:30:15 [ERROR] [OrderProcessor] Batch stalled: SP-API down, 350 orders queued to pending_sync'))
lines.append(('order-service.log', '2026-08-06 12:35:42 [CRITICAL] [OrderProcessor] Queue overflow risk: pending_sync at 830, limit 1000'))
lines.append(('order-service.log', '2026-08-06 13:00:05 [INFO] [OrderProcessor] SP-API restored, draining 830 backlog orders'))
lines.append(('order-service.log', '2026-08-06 13:15:30 [INFO] [OrderProcessor] Backlog cleared: 830 orders synced'))

# payment-service.log — 关联真实SKU
for sku in skus[:8]:
    h, m, s = random.randint(8, 22), random.randint(0, 59), random.randint(0, 59)
    day = random.randint(6, 8)
    if random.random() < 0.2:
        lines.append(('payment-service.log', f'2026-08-{day:02d} {h:02d}:{m:02d}:{s:02d} [ERROR] [PaymentGateway] Payment declined: SKU {sku}, reason: insufficient_funds'))
    else:
        amt = round(random.uniform(19, 200), 2)
        lines.append(('payment-service.log', f'2026-08-{day:02d} {h:02d}:{m:02d}:{s:02d} [INFO] [PaymentGateway] Payment captured: SKU {sku}, amount USD {amt}'))

lines.append(('payment-service.log', '2026-08-06 12:30:22 [WARN] [PaymentGateway] Txn spike: 280 txns/5min, p95 latency 2.3s (threshold 1.0s)'))
lines.append(('payment-service.log', '2026-08-06 12:35:45 [ERROR] [PaymentGateway] Circuit breaker OPEN: SP-API auth failure, payments queued'))

# inventory-service.log — 关联真实SKU的库存状态
for sku in skus[:5]:
    h, m, s = random.randint(8, 22), random.randint(0, 59), random.randint(0, 59)
    day = random.randint(6, 8)
    stock = random.randint(0, 30)
    level = 'WARN' if stock < 10 else 'INFO'
    lines.append(('inventory-service.log', f'2026-08-{day:02d} {h:02d}:{m:02d}:{s:02d} [{level}] [StockMonitor] SKU {sku} stock: {stock} units (safety: 50)'))

lines.append(('inventory-service.log', '2026-08-06 01:00:10 [WARN] [StockMonitor] 5 SKUs inventory sync failed: product mapping missing'))
lines.append(('inventory-service.log', '2026-08-07 12:30:18 [WARN] [StockMonitor] 20 SKUs flagged as delisted: Amazon Listing removed'))

# 写入
import os
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
services = ['sp-api', 'order-service', 'payment-service', 'inventory-service']
for svc in services:
    svc_lines = [l[1] for l in lines if l[0] == f'{svc}.log']
    svc_lines.sort()
    with open(os.path.join(log_dir, f'{svc}.log'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(svc_lines))
    print(f'{svc}.log: {len(svc_lines)} lines')

print(f'\nTotal: {len(lines)} log entries across 4 services')
print('Data sources: order IDs from real MySQL orders, SKUs from real order_items')
