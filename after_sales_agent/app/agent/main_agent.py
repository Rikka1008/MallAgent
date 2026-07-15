"""Deep Agent 主智能体构建器。"""

from typing import Any

from agent.context import AgentRuntimeContext
from agent.deep_subagents import build_subagents
from agent.prompts import MAIN_SYSTEM_PROMPT, conversation_memory_prompt
from config import LlmConfig
from deepagents import create_deep_agent
from langchain_deepseek import ChatDeepSeek


def build_main_agent(checkpointer, model: Any | None = None):
    """构建使用同一 DeepSeek 模型的主智能体和六个子智能体。"""

    active_model = model or build_deepseek_model()
    return create_deep_agent(
        model=active_model,
        system_prompt=MAIN_SYSTEM_PROMPT,
        tools=[],
        subagents=build_subagents(active_model),
        checkpointer=checkpointer,
        context_schema=AgentRuntimeContext,
        middleware=[conversation_memory_prompt],
        name="ecommerce_after_sales_agent",
    )


def build_deepseek_model() -> ChatDeepSeek:
    """根据生产配置创建 DeepSeek 对话模型，不在此处输出任何密钥。"""

    config = LlmConfig.require_main_model()
    return ChatDeepSeek(
        model=config["model"],
        api_key=config["api_key"],
        base_url=config["base_url"],
        temperature=config["temperature"],
        max_tokens=config["max_tokens"],
        timeout=config["request_timeout_seconds"],
    )
