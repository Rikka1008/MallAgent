"""Deep Agent 图入口。"""
from agent.context import AgentRuntimeContext
from agent.main_agent import build_main_agent

AgentGraphContext = AgentRuntimeContext

def build_checkpointed_agent_graph(checkpointer):
    """返回绑定检查点的 Deep Agent 图。"""
    return build_main_agent(checkpointer)
