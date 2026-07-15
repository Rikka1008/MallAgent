"""Deep Agent 聊天调用服务。"""

from agent.context import AgentRuntimeContext
from langchain_core.messages import AIMessage, HumanMessage


class ChatService:
    def __init__(self, main_agent):
        self.main_agent = main_agent

    async def reply(
        self, message: str, thread_id: str, context: AgentRuntimeContext
    ) -> str:
        result = await self.main_agent.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            {"configurable": {"thread_id": thread_id}},
            context=context,
        )
        return _last_ai_content(result.get("messages", []))


def _last_ai_content(messages: list) -> str:
    """只提取主智能体最终生成的文本，不输出子智能体内部内容。"""

    for message in reversed(messages):
        if isinstance(message, AIMessage) and isinstance(message.content, str):
            return message.content
    return "暂时无法生成回复，请稍后再试。"
