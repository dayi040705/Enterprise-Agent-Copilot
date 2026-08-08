-- ============================================================
-- ClickHouse OLAP Schema — 电商运营分析层
-- 企业架构: MySQL(OLTP) + ClickHouse(OLAP) 双引擎
--
-- 面试金句:
--   "MySQL 存订单和库存,处理实时交易。ClickHouse 存广告效果、
--    销量趋势和排名历史,跑聚合查询。Agent 查 MySQL 看当前状态,
--    查 ClickHouse 看趋势变化。两个不是替代关系,是分工。"
-- ============================================================

-- 1. 广告效果表 (日均百万级写入)
CREATE TABLE ad_performance (
    date        Date,
    sku         String,
    campaign_id String,
    impressions UInt32,          -- 曝光量
    clicks      UInt32,          -- 点击量
    spend       Decimal(10,2),   -- 花费
    orders      UInt32,          -- 广告带来的订单
    sales       Decimal(10,2)    -- 广告带来的销售额
) ENGINE = MergeTree()
ORDER BY (date, sku)
PARTITION BY toYYYYMM(date);

-- 2. 日销量趋势表 (T+1 批量写入)
CREATE TABLE sales_daily (
    date            Date,
    sku             String,
    units_sold      UInt32,          -- 售出件数
    revenue         Decimal(12,2),   -- 销售额
    refund_units    UInt16,          -- 退款件数
    refund_rate     Decimal(5,2),    -- 退款率(%)
    avg_price       Decimal(10,2)    -- 均价
) ENGINE = SummingMergeTree()
ORDER BY (date, sku);

-- 3. Listing 排名历史 (每日快照)
CREATE TABLE listing_rankings (
    date          Date,
    sku           String,
    keyword       String,            -- 搜索关键词
    organic_rank  UInt16,            -- 自然排名
    ad_rank       UInt16,            -- 广告排名
    rating        Decimal(2,1),      -- 当日评分
    review_count  UInt16             -- 累计评价数
) ENGINE = MergeTree()
ORDER BY (date, sku, keyword);

-- 4. 数据同步日志 (从 MySQL ETL 到 ClickHouse 的流水)
CREATE TABLE sync_etl_log (
    batch_time  DateTime,
    source      String,              -- 'MySQL'
    table_name  String,
    rows_synced UInt32,
    latency_sec UInt32               -- 同步延迟(秒)
) ENGINE = MergeTree()
ORDER BY batch_time;
