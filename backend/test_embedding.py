from services.embedding import embedding_texts


text = "员工请假需要审批"


vector = embedding_texts([text])[0]  # 传入列表，取第一个结果


print(len(vector))

print(vector[:5])