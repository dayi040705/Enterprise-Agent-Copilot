"""测试: Prompt 模板正确性"""

def test_rag_prompts_exist():
    """所有 prompt 常量都能正常导入且非空"""
    from services import prompt

    assert prompt.RAG_SYSTEM_PROMPT
    assert prompt.RAG_USER_TEMPLATE
    assert prompt.QUERY_REWRITE_SYSTEM_PROMPT
    assert prompt.QUERY_REWRITE_USER_TEMPLATE
    assert prompt.FAITHFULNESS_JUDGE_PROMPT
    assert prompt.RELEVANCY_JUDGE_PROMPT


def test_rag_user_template_format():
    """RAG_USER_TEMPLATE 必须包含三个占位符"""
    from services.prompt import RAG_USER_TEMPLATE

    result = RAG_USER_TEMPLATE.format(
        history_section="历史对话内容",
        context_text="检索到的参考资料",
        question="用户问题"
    )
    assert "历史对话内容" in result
    assert "检索到的参考资料" in result
    assert "用户问题" in result


def test_judge_prompts_format():
    """Judge prompt 模板必须支持占位符替换"""
    from services.prompt import FAITHFULNESS_JUDGE_PROMPT, RELEVANCY_JUDGE_PROMPT

    f_result = FAITHFULNESS_JUDGE_PROMPT.format(
        context_text="上下文内容",
        answer="模型回答"
    )
    assert "上下文内容" in f_result
    assert "模型回答" in f_result

    r_result = RELEVANCY_JUDGE_PROMPT.format(
        question="问题",
        answer="回答"
    )
    assert "问题" in r_result
    assert "回答" in r_result
