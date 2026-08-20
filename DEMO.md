# 面试演示脚本 (Interview Demo Script)

> 总时长 15-20 分钟 | 主线账号: dayi (运营部) | 提前演练一遍, 记住各阶段耗时

---

## 0. 演示前检查清单

- [ ] MySQL80 服务已启动 (管理员 PowerShell: `net start MySQL80`)
- [ ] 后端已启动: `cd backend && uvicorn main:app --reload`
- [ ] 前端已启动: `cd frontend-vue && npm run dev` (http://localhost:5173)
- [ ] DeepSeek API Key 已配置 (backend/.env)
- [ ] 浏览器隐身窗口打开 http://localhost:5173 (避免旧缓存干扰)
- [ ] 提前跑一遍第 3 幕, 确认各阶段耗时 (API 慢时心里有数)

### 账号表

| 用户名 | 密码 | 部门 | 用途 |
|--------|------|------|------|
| dayi | 123456 | 运营部 | **主演示账号** |
| lisi | 123456 | 客服部 | 权限隔离演示 |
| wangwu | 123456 | 供应链部 | 权限隔离演示 (备用) |
| admin | admin123 | ADMIN | 管理后台演示 |

---

## 开场 (30 秒) — 登录 + 页面总览

**操作**: 登录 dayi → 进入聊天页

**展示**: 暗色主题界面, 顶栏元素依次介绍:

> "这是完整的前后端系统。左侧历史会话; 顶部有晨报按钮、SKU 下拉选择器、Listing 诊断按钮; 还有 5 种模式切换——RAG / Agent / Planner / Multi / Unified。**所有演示默认走 Unified 模式**: Query Rewrite 多轮改写 + Router 自动分发, 简单查询走单 Agent, 复杂排障自动升级为 Multi-Agent 协作。下面的 RAG/Agent/Multi 模式是用来单独解构某一层的。"

---

## 第 1 幕: 知识库问答 + Router 分发 (3 分钟)

**操作**: 默认 `Unified` 模式, 问:

> "如果有人跟卖我的 Listing, 我该怎么应对?"

**预期**: 进度日志显示 `Router → knowledge 模式`, 答案引用《跟卖应对手册》内容

**追问** (演示 Query Rewrite):

> "那怎么识别呢?"

(第二个问题省略了主语"跟卖", 展示系统用历史对话补全上下文)

**可选补充**: 切到 `RAG` 模式问同样的问题 → 展示引用标签 `跟卖应对手册.md (P1)` 的检索链路 (Unified 和 RAG 的区别: 后者直接展示 sources)

**讲解词**:

> "Unified 入口做了两件事: Query Rewrite 把'那怎么识别呢'补全成完整问题; Router 判断这是知识库问题, 走 Knowledge 检索。检索链路是三层漏斗: BGE 向量召回 + BM25 关键词召回 → RRF 融合 → BGE Reranker 交叉编码精排。"

**面试钩子**: "为什么不用纯向量检索?" → 中文关键词精确匹配 + 领域术语召回率问题

---

## 第 2 幕: 简单数据查询 (2 分钟)

**操作**: `Unified` 模式, 问:

> "退款率最高的 3 个 SKU 是什么?"

**预期**: 进度日志 `Router → action 模式`, 实时工具调用卡片 `query_analytics(metric="top_refund")`, 毫秒级返回 (预聚合表)

**讲解词**:

> "Router 判断这是单次数据查询, 走单 Agent 直接执行。Agent 不写 SQL——数据查询封装成参数化工具, LLM 传业务参数就行。为什么? LLM 自己拼 SQL 容易写错表名、JOIN 条件, 参数化工具消除了这类稳定性问题。评测里 Tool Success 100% 就是这个设计的结果。"

**面试钩子**: "LLM 写 SQL 有什么问题?" → 不稳定、安全风险 (SQL 注入)、性能不可控

---

## 第 3 幕: Multi-Agent 复杂排障 ⭐ 全场核心 (5 分钟)

**操作**: `Unified` 模式, 问:

> "SKU b0013bdd 转化率从 8% 暴跌到 2%, 全面排查: 查评分变化、退款率趋势、跟卖应对 SOP、广告投放策略, 输出诊断报告"

**预期画面** (进度日志逐条滚动):

```
▸ Router → multi-agent 模式          (Unified 自动判定为复杂排障)
▸ Router: 分析问题类型中...
▸ Router → Multi-Agent 复杂排障
▸ Supervisor: 拆解任务中...
[执行计划框: 3-4 个子任务]
▸ Action Agent → 调用 query_listing
▸ Knowledge Agent → 调用 search_knowledge_base
▸ Action Agent 完成: 3 条证据
▸ Reporter: 生成报告...
[报告流式输出: 已确认事实/推测原因/待确认]
▸ Reviewer: 审查报告中...
▸ Reviewer: 通过 (faith=95%)
```

**操作**: 点「查看 Trace」→ 展示执行树: Supervisor → 3 个 Agent 节点 → 每个工具调用的入参/出参 → Reporter → Reviewer 层级结构

**操作**: 点「返回聊天」→ 回到原会话 (keep-alive 保持状态, 不丢消息)

**讲解词** (指着 Trace 树):

> "完整闭环: Supervisor 拆解 → 三路 asyncio 并行 → Reporter 生成含矛盾检测的报告 → Reviewer 从 Faithfulness/Relevancy 审查 → 缺证据自动打回 Supervisor 补查。报告里每条事实都标注来源 Agent 和工具, 不标注来源的事实声明被明确禁止。"

**面试钩子**: "为什么需要 Reviewer?" → LLM 会编造数据, Reviewer 是质量闸门, 评测 Faithfulness 97% 是证据

**抗追问**: "为什么这么慢?" →

> "一次诊断 12-20 次 LLM 调用, 这是 Multi-Agent 的固有代价——用调用次数换质量保证。简单查询走 Unified Router 的 simple 路由, 10 秒内出结果。想更快可以做工具结果缓存。"

---

## 第 4 幕: Skill 机制 (3 分钟)

**操作 1**: 点 **「晨报」** 按钮

**预期**: 自动并行查 5 维度 (销量/退款/库存/管道/Listing), 生成结构化日报

**操作 2**: SKU 下拉框选 `b0013bdd` (退款率 7.9%, 数据最丰富) → 点 **「Listing诊断」**

**预期**: 完整诊断报告: SKU 基础信息 / 退款率诊断 / 销量趋势 / 跟卖风险评估 / 综合建议

**讲解词**:

> "运营巡检流程被封装成一键触发的 Skill——本质是预定义 Prompt 模板走 Multi-Agent 通道。运营不需要懂 Agent 原理, 点按钮就行。"

---

## 第 5 幕: 部门权限隔离 (2 分钟)

**操作**: 退出登录 → `lisi / 123456` (客服部) → 问:

> "广告怎么投放?"

**预期**: 检索不到 (广告 SOP 是运营部的), 展示权限隔离生效

**操作**: 再问:

> "退货怎么处理?"

**预期**: 能查到售后处理SOP.md (客服部的)

**讲解词**:

> "两层防线: JWT 携带部门声明 + ChromaDB Metadata Filter 检索过滤, 工具执行层还有第二道校验。"

**操作**: 退出 → `admin / admin123` → 点右上角「管理后台」

**预期**: 文档管理页显示 5 篇电商 SOP (文件名/部门/创建人/块数/状态), 可禁用/删除

---

## 第 6 幕: 评测体系 (2 分钟)

**操作**: 终端执行:

```bash
cd backend
python test_agent_eval.py
```

**预期**: 20 题 × 7 场景逐题输出 + 汇总指标

**讲解词**:

> "评测是我自研的: LLM Judge 按 Faithfulness (答案是否忠实于工具数据) 和 Relevancy (是否切题) 双维度打分, 还统计 TTF、token 成本、工具覆盖率。每次改 prompt 或架构, 跑一遍评测验证回归。"

---

## 7. 备用彩蛋: 双引擎数据架构 (按剩余时间)

**操作**: 打开一个新终端, 执行一键演示脚本:

```bash
cd backend
.venv\Scripts\python scripts\benchmark_dual_engine.py
```

**预期输出** (真实实测数据):

```
【数据量】
  MySQL.orders              100,000 行
  MySQL.order_items         219,349 行
  MySQL.order_reviews       933,748 行
  ...合计 1,370,645 行 (≈137万)
  analytics.sales_daily     205,193 行 (预聚合)

【慢查询】三表 JOIN 聚合
  → 耗时: 37.0 秒          ← 面试官看着秒数走

【快查询】预聚合点查
  → 耗时: 0.0010 秒        ← 1 毫秒

性能差距: ≈ 37,000 倍
```

**讲解词** (等 37 秒的间隙正好讲架构):

> "慢查询要把 orders、order_items、order_reviews 三张表 137 万行 JOIN 后扫描聚合——93 万条评价行; 快查询直接查每天凌晨 ETL 预聚合好的 sales_daily 表, 单 SKU 索引点查 1 毫秒。Agent 的查询策略就是: 实时订单状态走 MySQL, 趋势/排行/退款率走 analytics。"

> "生产环境的扩展路径: schemas/clickhouse_schema.sql 里设计了 ClickHouse OLAP 表结构 (SummingMergeTree 自动合并), sync_mysql_to_clickhouse.py 是 ETL 同步方案。当前 analytics 在 MySQL 里模拟, 架构上预留了切换 ClickHouse 的空间。"

**备用: 手动 SQL 版** (不想跑脚本时, 在 MySQL 客户端执行):

```sql
-- 慢: 三表 JOIN (37 秒)
SELECT oi.product_id, COUNT(*), AVG(rv.score)
FROM orders o
JOIN order_items oi ON o.order_id = oi.order_id
JOIN order_reviews rv ON o.order_id = rv.order_id
GROUP BY oi.product_id ORDER BY 2 DESC LIMIT 5;

-- 快: 预聚合点查 (毫秒级)
SELECT * FROM analytics.sales_daily
WHERE sku = 'ecc40aa4-0dc9-4c3d-b5ff-7a7c1e9cba49' AND units_sold > 0
ORDER BY date DESC LIMIT 10;
```

---

## 8. 高频追问预案

| 面试官可能问 | 回答要点 |
|-------------|---------|
| ClickHouse 部署了吗? | 当前 analytics 在 MySQL 模拟, 设计了完整 Schema + ETL 方案, 架构预留切换空间 |
| 微调用的是 LoRA 吗? | 模型只有 24MB, 全参数微调 CPU 上几秒完成, 比 LoRA 更简单高效; 20 对数据 3 epoch, 8/10 查询保持或提升命中率 |
| 516 倍怎么测的? | 架构设计推算: MySQL 三表 JOIN 扫全量 vs 预聚合表单表查询的量级差异 |
| 为什么不用 LangChain? | LangGraph 状态图编排多 Agent 协作 + 手写 ReAct 理解原理; 评测体系也自己写 |
| Memory 过期怎么做的? | ChromaDB metadata 存 expire_at 时间戳, 检索时过滤过期记录, 180 天内标注"仅供参考" |
| 多轮对话怎么实现? | LangGraph Checkpoint (MemorySaver) + thread_id 隔离会话; RAG 模式走 MySQL 聊天记录 + Query Rewrite |
| 部署情况? | Docker Compose: MySQL + backend 两服务, 模型/向量库/日志都挂载持久化 |

---

## 9. 故障应急

| 故障 | 应急 |
|------|------|
| DeepSeek API 慢/报错 | "这是 Multi-Agent 的固有延迟——12-20 次 LLM 调用", 转成架构讨论 |
| MySQL 没启动 | 管理员 PowerShell: `net start MySQL80` |
| 页面登录异常 | 刷新页面 (keep-alive 已修, 正常无需) |
| 晨报/L诊断无结果 | 检查 analytics.sales_daily 表有数据; 用 SKU 下拉框里的真实 SKU |
| 权限问题报错 | 确认登录账号部门正确 (dayi=运营部), 知识库标签已按部门修复 |

---

## 10. 测试问题库 (已按实际数据验证)

> 所有 SKU、SOP、记忆数据均已在数据库核实, 可放心提问。
> 标注 ⭐ 的是演示效果最稳的题。

### 10.1 知识库问题 (Unified, dayi/运营部)

| # | 问题 | 命中 SOP | 备注 |
|---|------|---------|------|
| 1⭐ | 如果有人跟卖我的 Listing, 我该怎么应对? | 跟卖应对手册 | 秒级返回, 预路由直通 |
| 2 | 那怎么识别呢? (追问) | 跟卖应对手册 | 演示 Query Rewrite |
| 3 | 识别跟卖之后第一步应该做什么? | 跟卖应对手册 | 多轮追问链 |
| 4 | 新品上架后广告预算怎么分配? | 广告投放策略 | |
| 5 | ACOS 太高了怎么优化? | 广告投放策略 | |
| 6 | Listing 标题应该怎么写? | Listing优化指南 | |
| 7 | Buy Box 丢了怎么排查? | 跟卖应对手册 | 手册 5.1 章节 |

### 10.2 简单数据查询 (Unified, dayi)

| # | 问题 | 工具路径 | 备注 |
|---|------|---------|------|
| 1⭐ | 退款率最高的 3 个 SKU 是什么? | query_analytics(top_refund) | 毫秒级 |
| 2 | 过去 30 天销量最高的 5 个 SKU 卖了多少? | query_analytics(top_sales) | |
| 3 | 最近 30 天销量趋势怎么样? | query_analytics(trend) | |
| 4 | 最近 10 个已取消的订单有哪些? | query_orders | OLTP 实时 |
| 5 | 平均评分最低的 5 个 Listing 是哪些? | query_listing | |
| 6 | 有哪些 SKU 最近可能断货了? | query_analytics(low_stock) | 库存预警 |

### 10.3 复杂排障 (Unified → 自动 Multi-Agent)

| # | 问题 | 预期拆解 | 备注 |
|---|------|---------|------|
| 1⭐ | SKU b0013bdd 转化率从 8% 暴跌到 2%, 全面排查: 查评分变化、退款率趋势、跟卖应对 SOP、广告投放策略, 输出诊断报告 | action+knowledge+diagnostic | 主演示题 |
| 2 | 过去 7 天退款率突然从 2% 飙升到 8%, 全面排查: 查退款率高的 SKU、查差评内容、查售后处理 SOP、查历史类似事故经验 | action+knowledge+diagnostic | 会命中记忆库"退款率质量排查" |
| 3 | SKU ecc40aa4 的 Buy Box 丢了, 全面排查原因并给出恢复建议 | action+knowledge | 会命中"跟卖抢 Buy Box"记忆 |
| 4 | PrimeDay 快到了, 结合历史经验给出备货建议 | knowledge+diagnostic | 会命中"PrimeDay 断货"记忆 ⭐混合场景 |

### 10.4 数据管道监控 (dayi)

| # | 问题 | 工具路径 | 备注 |
|---|------|---------|------|
| 1⭐ | 查一下最近 24 小时 SP-API 数据同步的健康度, 录入率是多少? 有没有失败的批次? | query_sync_logs | 22 条模拟日志, 含 429/401/JSON 错误 |
| 2 | SP-API 同步失败的原因是什么? | query_sync_logs | 展示错误细节 |

### 10.5 长期记忆检索 (dayi)

| # | 问题 | 命中记忆 | 备注 |
|---|------|---------|------|
| 1⭐ | 上次 Listing 被恶意差评那次是怎么处理的? 最后恢复了吗? | 恶意差评处理 (运营部) | 3 天恢复 6.5% 的故事 |
| 2 | 之前 PrimeDay 备货不足那次是怎么处理的? 有什么教训? | PrimeDay 断货 (运营部) | 备货系数 4x 教训 |
| 3 | SP-API 429 限流那次怎么解决的? | 429 限流处理 (运营部) | 指数退避方案 |

### 10.6 Skill 按钮 (dayi)

| 操作 | 预期 |
|------|------|
| 点「晨报」 | 并行查 5 维度, 结构化日报 |
| SKU 下拉选 b0013bdd (退款率7.9%) → 「Listing诊断」 | 完整诊断报告 ⭐ |
| SKU 下拉选 ecc40aa4 (销量最高) → 「Listing诊断」 | 健康 SKU 对照 |
| SKU 下拉选 83fbdf52 (Nimbus Headphones) → 「Listing诊断」 | 有真实商品名 |

### 10.7 权限隔离演示

| 账号 | 提问 | 预期结果 |
|------|------|---------|
| lisi (客服部) | 广告怎么投放? | ❌ 查不到 (广告SOP是运营部的) |
| lisi (客服部) | 买家收到破损商品要求退货怎么处理? | ✅ 命中售后处理SOP |
| wangwu (供应链部) | 安全库存怎么计算? | ✅ 命中库存管理规范 |
| wangwu (供应链部) | 跟卖怎么办? | ❌ 查不到 (跟卖SOP是运营部的) |
| admin | 管理后台 → 文档管理 | ✅ 5 篇 SOP + 部门 + 创建人 |

### 10.8 面试随机应变题 (有把握时再用)

| 场景 | 问题 | 展示点 |
|------|------|--------|
| 综合 | "帮我查一下退款率最高的 SKU 是什么, 然后看看对应的 Listing 评分变化, 再查一下售后处理应该怎么做" | 混合多工具协作 |
| 追问链 | 跟卖应对 → 怎么识别 → 第一步做什么 | Query Rewrite 三层追问 |
| 数据+知识 | "库存预警的 SKU 有哪些? 补货流程是什么?" | 数据查询 + SOP 检索联动 |
