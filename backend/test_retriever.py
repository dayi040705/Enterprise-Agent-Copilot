from services.retriever import retrieve_context


result = retrieve_context(
    "员工请假需要什么流程？"
)


for item in result:

    print("----------------")

    print(item)