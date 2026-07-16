from agent import deep_subagents


def test_six_subagents_have_disjoint_business_tools(monkeypatch):
    def fake_create_agent(*, model, system_prompt, tools, name):
        return {
            "model": model,
            "system_prompt": system_prompt,
            "tools": tools,
            "name": name,
        }

    monkeypatch.setattr(deep_subagents, "create_agent", fake_create_agent)

    agents = deep_subagents.build_subagents(model=object())

    assert [item["name"] for item in agents] == [
        "product_agent",
        "order_agent",
        "logistics_agent",
        "refund_agent",
        "after_sales_agent",
        "policy_agent",
    ]
    assert [tool.name for tool in agents[0]["runnable"]["tools"]] == ["search_products"]
    assert [tool.name for tool in agents[1]["runnable"]["tools"]] == [
        "list_orders",
        "get_order",
    ]
    assert [tool.name for tool in agents[2]["runnable"]["tools"]] == ["get_logistics"]
    assert [tool.name for tool in agents[3]["runnable"]["tools"]] == ["get_refund_status"]
    assert [tool.name for tool in agents[4]["runnable"]["tools"]] == [
        "submit_after_sales_request"
    ]
    assert [tool.name for tool in agents[5]["runnable"]["tools"]] == ["search_policy"]


def test_subagent_prompts_require_context_only_and_forbid_invention(monkeypatch):
    monkeypatch.setattr(
        deep_subagents,
        "create_agent",
        lambda **kwargs: kwargs,
    )

    agents = deep_subagents.build_subagents(model=object())

    for agent in agents:
        prompt = agent["runnable"]["system_prompt"]
        assert "不要生成面向用户的最终答复" in prompt
        assert "不得编造" in prompt

    assert "先调用 `search_products`" in agents[0]["runnable"]["system_prompt"]
    assert "我有哪些订单" in agents[1]["runnable"]["system_prompt"]
    assert "`list_orders`" in agents[1]["runnable"]["system_prompt"]
    assert "完整且经过校验" in agents[4]["runnable"]["system_prompt"]


def test_after_sales_prompt_limits_submission_success_wording(monkeypatch):
    monkeypatch.setattr(deep_subagents, "create_agent", lambda **kwargs: kwargs)

    prompt = deep_subagents.build_subagents(model=object())[4]["runnable"]["system_prompt"]

    assert "等待后台审核" in prompt
    assert "申请提交成功不代表退款到账" in prompt
    assert "不得承诺退款金额或到账结果" in prompt


def test_refund_prompt_explains_discount_instead_of_reporting_false_mismatch(monkeypatch):
    monkeypatch.setattr(deep_subagents, "create_agent", lambda **kwargs: kwargs)

    prompt = deep_subagents.build_subagents(model=object())[3]["runnable"]["system_prompt"]

    assert "原价、优惠金额、实付金额和申请退款金额" in prompt
    assert "退款金额与实付金额一致" in prompt
    assert "不得将原价与申请退款金额直接比较" in prompt


def test_order_prompt_preserves_deterministic_list_and_after_sales_status(monkeypatch):
    monkeypatch.setattr(deep_subagents, "create_agent", lambda **kwargs: kwargs)

    prompt = deep_subagents.build_subagents(model=object())[1]["runnable"]["system_prompt"]

    assert "rendered_markdown" in prompt
    assert "不得省略任何订单" in prompt
    assert "售后状态优先" in prompt


def test_knowledge_subagents_rewrite_query_before_search(monkeypatch):
    monkeypatch.setattr(deep_subagents, "create_agent", lambda **kwargs: kwargs)

    agents = deep_subagents.build_subagents(model=object())

    for index in (0, 5):
        prompt = agents[index]["runnable"]["system_prompt"]
        assert "直接改写" in prompt
        assert "只作为工具的 `query` 参数" in prompt
        assert "指代无法唯一确定" in prompt
        assert "不得增加对话中不存在" in prompt

    for index in (1, 2, 3, 4):
        assert "直接改写" not in agents[index]["runnable"]["system_prompt"]
