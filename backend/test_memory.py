"""查看长期记忆内容"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
from services.chroma import client

col = client.get_or_create_collection('agent_memory')
data = col.get()
print(f"Total: {len(data['ids'])} records")
for i, (id_, doc, meta) in enumerate(zip(data['ids'], data['documents'] or [], data['metadatas'] or [])):
    print(f"[{i+1}] {meta.get('time','')[:16]} | {meta.get('department','')} | {doc[:120] if doc else ''}")
