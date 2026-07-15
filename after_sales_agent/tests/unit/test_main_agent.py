from agent import main_agent


def test_main_prompt_declares_all_six_task_targets():
    for name in (
        "product_agent",
        "order_agent",
        "logistics_agent",
        "refund_agent",
        "after_sales_agent",
        "policy_agent",
    ):
        assert f'task("{name}"' in main_agent.MAIN_SYSTEM_PROMPT


def test_main_prompt_routes_order_list_questions_to_order_agent():
    assert "我的订单" in main_agent.MAIN_SYSTEM_PROMPT
    assert "最近订单" in main_agent.MAIN_SYSTEM_PROMPT
    assert 'task("order_agent"' in main_agent.MAIN_SYSTEM_PROMPT


def test_main_prompt_requires_context_complete_knowledge_retrieval_tasks():
    prompt = main_agent.MAIN_SYSTEM_PROMPT

    assert "消除指代" in prompt
    assert "必要的最近对话" in prompt
    assert "保留订单号、SKU、金额和时间" in prompt
    assert "不得补造事实" in prompt


def test_main_prompt_forbids_speculative_policy_wording():
    prompt = main_agent.MAIN_SYSTEM_PROMPT

    assert "不得向用户提及政策资料未覆盖或未明确" in prompt
    assert "按常规" in prompt
    assert "通常可以" in prompt
    assert "只能陈述工具返回的事实" in prompt


def test_main_prompt_compares_refund_with_paid_amount_not_original_price():
    prompt = main_agent.MAIN_SYSTEM_PROMPT

    assert "申请退款金额应与实付金额比较" in prompt
    assert "不得与商品原价直接比较" in prompt
    assert "促销优惠造成的差额不是金额不匹配" in prompt


def test_main_agent_uses_runtime_context_and_six_subagents(monkeypatch):
    captured = {}
    fake_model = object()
    fake_checkpointer = object()

    def fake_create_deep_agent(**kwargs):
        captured.update(kwargs)
        return "compiled-agent"

    monkeypatch.setattr(main_agent, "create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr(main_agent, "build_subagents", lambda model: [{"model": model}])

    result = main_agent.build_main_agent(checkpointer=fake_checkpointer, model=fake_model)

    assert result == "compiled-agent"
    assert captured["model"] is fake_model
    assert captured["checkpointer"] is fake_checkpointer
    assert captured["context_schema"].__name__ == "AgentRuntimeContext"
    assert captured["subagents"] == [{"model": fake_model}]
    assert len(captured["middleware"]) == 1


def test_graph_delegates_to_main_agent_builder(monkeypatch):
    from agent import graph

    fake_checkpointer = object()
    monkeypatch.setattr(graph, "build_main_agent", lambda checkpointer: ("agent", checkpointer))

    assert graph.build_checkpointed_agent_graph(fake_checkpointer) == (
        "agent",
        fake_checkpointer,
    )
