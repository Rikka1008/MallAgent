from dataclasses import dataclass

from agent.context import AgentRuntimeContext
from langchain_core.messages import AIMessage
from services.chat_service import ChatService
from tests.fakes import FakeEcommerceGateway


@dataclass
class FakeAgent:
    async def ainvoke(self, _input, _config, context):
        assert context.user_id == "U100"
        return {"messages": [AIMessage(content="主智能体回复")]}


async def test_chat_service_returns_only_main_agent_final_content():
    service = ChatService(main_agent=FakeAgent())
    context = AgentRuntimeContext(
        user_id="U100", session_id="S100", gateway=FakeEcommerceGateway()
    )

    result = await service.reply("查询订单", "S100", context)

    assert result == "主智能体回复"
