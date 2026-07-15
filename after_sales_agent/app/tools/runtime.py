from __future__ import annotations

from agent.context import AgentRuntimeContext
from langchain.tools import ToolRuntime


def get_runtime_context(
    runtime: ToolRuntime[AgentRuntimeContext],
) -> AgentRuntimeContext:
    """从 LangGraph 工具运行时提取服务端上下文。"""

    return runtime.context
