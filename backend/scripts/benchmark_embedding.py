"""微调前后 Embedding 检索效果对比"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sentence_transformers import SentenceTransformer
import chromadb
import time

# 加载两个模型
base_model = SentenceTransformer("BAAI/bge-small-zh")
try:
    lora_model = SentenceTransformer("./models/bge-small-zh-ecommerce")
    has_lora = True
except:
    print("LoRA model not found — run finetune_embedding.py first")
    has_lora = False

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_collection("knowledge")

# 测试查询 — 从评测题里抽
test_queries = [
    "退货怎么处理",
    "跟卖怎么办",
    "广告投放策略",
    "Listing怎么优化",
    "库存低于安全线",
    "ACOS太高了",
    "Buy Box丢了",
    "差评处理流程",
    "退款率最高的SKU",
    "转化率暴跌怎么办",
]

print("=" * 60)
print(f"{'Query':<25s} {'Base':>8s} {'LoRA':>8s} {'Improve':>8s}")
print("=" * 60)

for query in test_queries:
    vec_base = base_model.encode(query)
    vec_lora = lora_model.encode(query) if has_lora else vec_base

    r_base = collection.query(query_embeddings=[vec_base], n_results=1,
                              include=["metadatas"])
    r_lora = collection.query(query_embeddings=[vec_lora], n_results=1,
                              include=["metadatas"]) if has_lora else r_base

    fname_base = r_base["metadatas"][0][0].get("filename", "?")
    fname_lora = r_lora["metadatas"][0][0].get("filename", "?") if has_lora else "?"

    # 判断是否命中正确的 SOP
    expected = {
        "退货": "售后处理SOP", "跟卖": "跟卖应对手册", "广告": "广告投放策略",
        "Listing": "Listing优化指南", "库存": "库存管理规范", "ACOS": "广告投放策略",
        "Buy Box": "跟卖应对手册", "差评": "售后处理SOP", "退款率": "广告投放策略",
        "转化率": "Listing优化指南",
    }
    exp = "?"
    for k, v in expected.items():
        if k in query:
            exp = v
            break

    imp = "N/A"
    if has_lora:
        base_ok = exp in str(fname_base)
        lora_ok = exp in str(fname_lora)
        if not base_ok and lora_ok:
            imp = "+SAME"
        elif base_ok and lora_ok:
            imp = "=SAME"
        elif not base_ok and not lora_ok:
            imp = "-MISS"

    print(f"{query:<25s} {str(fname_base)[:8]:>8s} {str(fname_lora)[:8]:>8s} {imp:>8s}")

print()
print("+SAME = LoRA corrected the retrieval (base was wrong)")
print("=SAME = Both correct (LoRA preserved quality)")
print("-MISS = Both missed (training data gap)")
