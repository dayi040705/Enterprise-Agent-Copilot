"""电商数据集导入脚本 — Kaggle U.S. E-Commerce → MySQL"""

import csv
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.mysql import engine, SessionLocal
from sqlalchemy import text

DATA_DIR = r"C:\Users\28298\Desktop\电商\数据集"

# ============================================================
# 1. 建表 SQL — 对标的 MySQL OLTP 层
# ============================================================

CREATE_TABLES = """
DROP TABLE IF EXISTS order_reviews;
DROP TABLE IF EXISTS order_payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS sellers;

-- 商品表
CREATE TABLE products (
    product_id VARCHAR(50) PRIMARY KEY,
    category VARCHAR(100),
    product_name VARCHAR(200),
    brand VARCHAR(100),
    weight_g INT,
    length_cm FLOAT,
    height_cm FLOAT,
    width_cm FLOAT,
    cost DECIMAL(10,2),
    price DECIMAL(10,2)
) CHARACTER SET utf8mb4;

-- 卖家表
CREATE TABLE sellers (
    seller_id VARCHAR(50) PRIMARY KEY,
    company_name VARCHAR(200),
    contact_name VARCHAR(100),
    city VARCHAR(50),
    state VARCHAR(10)
) CHARACTER SET utf8mb4;

-- 订单表
CREATE TABLE orders (
    order_id VARCHAR(50) PRIMARY KEY,
    customer_id VARCHAR(50),
    order_status VARCHAR(30),
    purchase_date DATETIME,
    approved_at DATETIME NULL,
    delivered_date DATETIME NULL,
    estimated_delivery DATETIME NULL,
    INDEX idx_status (order_status),
    INDEX idx_date (purchase_date)
) CHARACTER SET utf8mb4;

-- 订单明细
CREATE TABLE order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id VARCHAR(50),
    product_id VARCHAR(50),
    seller_id VARCHAR(50),
    quantity INT DEFAULT 1,
    price DECIMAL(10,2),
    freight DECIMAL(10,2),
    discount_rate DECIMAL(5,2) DEFAULT 0,
    INDEX idx_order (order_id),
    INDEX idx_product (product_id)
) CHARACTER SET utf8mb4;

-- 支付记录
CREATE TABLE order_payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id VARCHAR(50),
    payment_type VARCHAR(20),
    installments INT DEFAULT 1,
    amount DECIMAL(10,2),
    INDEX idx_order (order_id)
) CHARACTER SET utf8mb4;

-- 订单评价
CREATE TABLE order_reviews (
    review_id VARCHAR(50) PRIMARY KEY,
    order_id VARCHAR(50),
    score INT,
    comment_title VARCHAR(200),
    comment TEXT,
    creation_date DATETIME NULL,
    INDEX idx_order (order_id),
    INDEX idx_score (score)
) CHARACTER SET utf8mb4;
"""


def create_schema():
    """执行建表"""
    with engine.connect() as conn:
        for stmt in CREATE_TABLES.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
    print("MySQL 建表完成")


def batch_insert(table: str, columns: list[str], rows: list[list], batch_size: int = 5000):
    """批量插入"""
    if not rows:
        return 0

    placeholders = ", ".join([f":{c}" for c in columns])
    cols = ", ".join(columns)
    sql = f"INSERT IGNORE INTO {table} ({cols}) VALUES ({placeholders})"

    total = 0
    with engine.connect() as conn:
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            params = [dict(zip(columns, row)) for row in batch]
            conn.execute(text(sql), params)
            total += len(batch)
        conn.commit()

    return total


def import_csv(table: str, columns: list[str], filename: str,
               limit: int = None, skip_first: bool = True):
    """从 CSV 读数据并批量灌入 MySQL"""
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        print(f"  文件不存在: {filename}")
        return 0

    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        if skip_first:
            next(reader)  # 跳过表头
        for i, row in enumerate(reader):
            if limit and i >= limit:
                break
            # 只取需要的列，裁剪超长字段
            cleaned = []
            for val in row[:len(columns)]:
                if isinstance(val, str):
                    cleaned.append(val[:500] if len(val) > 500 else val)
                else:
                    cleaned.append(val)
            rows.append(cleaned)

    count = batch_insert(table, columns, rows)
    print(f"  {table}: {count} 条 ({filename})")
    return count


def _import_subset(table: str, cols: list[str], filename: str,
                    order_ids: set, col_map: dict, defaults: dict = None):
    """只导入 orders 里存在的记录, 支持列重映射 + 默认值"""
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        print(f"  文件不存在: {filename}")
        return 0

    n_cols = len(cols)
    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # 跳过表头
        for row in reader:
            oid = row[0]  # order_id 总在第一列
            if oid not in order_ids:
                continue

            mapped = [""] * n_cols
            for csv_idx, tbl_idx in col_map.items():
                val = row[csv_idx] if csv_idx < len(row) else ""
                if isinstance(val, str):
                    val = val[:500] if len(val) > 500 else val
                mapped[tbl_idx] = val

            # 应用默认值 (如 quantity=1)
            if defaults:
                for idx, default_val in defaults.items():
                    mapped[idx] = default_val

            rows.append(mapped)

    count = batch_insert(table, cols, rows)
    print(f"  {table}: {count} 条 ({filename})")
    return count


def import_data():
    """主导入流程"""
    print("=" * 50)
    print("开始导入电商数据集 → MySQL")
    print("=" * 50)

    # Step 1: 建表
    create_schema()

    # Step 2: 小表全量导入
    print("\n[小表] 全量导入...")
    import_csv("products", [
        "product_id", "category", "product_name", "brand",
        "weight_g", "length_cm", "height_cm", "width_cm", "cost", "price"
    ], "products.csv")

    import_csv("sellers", [
        "seller_id", "company_name", "contact_name", "city", "state"
    ], "sellers.csv")

    # Step 3: 订单表 — 导入最近 10 万条
    print("\n[订单] 导入 10 万条...")
    import_csv("orders", [
        "order_id", "customer_id", "order_status", "purchase_date",
        "approved_at", "delivered_date", "estimated_delivery"
    ], "orders.csv", limit=100_000)

    # Step 4: 获取已导入的 order_id 集合 (用于过滤子表)
    order_ids = set()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT order_id FROM orders"))
        for row in result:
            order_ids.add(row[0])
    print(f"\n  已导入 {len(order_ids)} 个订单, 过滤子表...\n")

    # Step 5: 子表 — 只导入匹配的 order_id (需要列映射)
    print("[子表] 过滤导入...")

    # order_payments: CSV(4列)直接对应表(4列)
    _import_subset("order_payments",
                   ["order_id", "payment_type", "installments", "amount"],
                   "order_payments.csv", order_ids,
                   col_map={0:0, 1:1, 2:2, 3:3})

    # order_reviews: CSV 7列 → 只取 review_id, order_id, score, title, message, date
    _import_subset("order_reviews",
                   ["review_id", "order_id", "score", "comment_title", "comment", "creation_date"],
                   "order_reviews.csv", order_ids,
                   col_map={0:0, 1:1, 2:2, 3:3, 4:4, 5:5})

    # order_items: CSV 8列(order_id,item_id,product_id,seller_id,shipping,price,freight,discount)
    # 表7列: order_id,product_id,seller_id,quantity,price,freight,discount_rate
    # quantity 不在 CSV 里, 默认=1
    _import_subset("order_items",
                   ["order_id", "product_id", "seller_id", "quantity", "price", "freight", "discount_rate"],
                   "order_items.csv", order_ids,
                   col_map={0:0, 2:1, 3:2, 4:4, 5:5, 6:6}, defaults={3: "1"})

    # Step 6: 统计
    print("\n" + "=" * 50)
    with engine.connect() as conn:
        for tbl in ["products", "sellers", "orders", "order_items", "order_payments", "order_reviews"]:
            r = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}"))
            print(f"  {tbl}: {r.fetchone()[0]} 条")
    print("=" * 50)
    print("导入完成!")


if __name__ == "__main__":
    import_data()
