from paper2tex.query import extract_arxiv_id, extract_title_query, parse_prompt_intent


def test_extract_title_from_cn_brackets():
    prompt = "请你帮我阅读这篇论文《Attention Is All You Need》并总结方法"
    assert extract_title_query(prompt) == "Attention Is All You Need"


def test_extract_arxiv_id_from_url():
    prompt = "请看一下 https://arxiv.org/abs/1706.03762v7"
    assert extract_arxiv_id(prompt) == ("1706.03762", "v7")


def test_parse_prompt_intent_with_section_hint():
    prompt = "帮我参考 attention is all you need 的实验部分写法"
    intent = parse_prompt_intent(prompt)
    assert intent.paper_query == "attention is all you need"
    assert intent.section_hint == "实验"
    assert "results" in intent.section_queries
    assert intent.action_hint == "imitate"


def test_parse_prompt_intent_prefers_quoted_title():
    prompt = 'Please read the paper "QLoRA: Efficient Finetuning of Quantized LLMs" and focus on the method section'
    intent = parse_prompt_intent(prompt)
    assert intent.paper_query == "QLoRA: Efficient Finetuning of Quantized LLMs"
    assert intent.section_hint == "method"
    assert "model architecture" in intent.section_queries


def test_extract_title_query_removes_simple_watch_verb():
    assert extract_title_query("帮我看 attention all you need") == "attention all you need"


def test_parse_prompt_intent_related_work_and_writing_style():
    intent = parse_prompt_intent("请参考某篇论文的相关工作写法")
    assert intent.section_hint == "相关工作"
    assert "related work" in intent.section_queries
    assert intent.action_hint == "imitate"
