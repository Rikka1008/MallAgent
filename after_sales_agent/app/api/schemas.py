from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """聊天请求体。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, description="会话编号")
    message: str = Field(min_length=1, description="用户输入的中文消息")


class MallLoginRequest(BaseModel):
    """Mall 会员登录请求。"""

    username: str = Field(min_length=1, max_length=64, description="Mall 会员账号")
    password: str = Field(min_length=1, max_length=128, description="Mall 会员密码")


class AuthenticatedUser(BaseModel):
    """通过 Mall 校验后的脱敏会员信息。"""

    user_id: str
    username: str


class AuthSessionResponse(BaseModel):
    """Agent 页面使用的会员认证状态。"""

    authenticated: bool
    user: AuthenticatedUser | None = None


class ChatResponse(BaseModel):
    """聊天响应体。"""

    session_id: str = Field(description="会话编号")
    reply: str = Field(description="Agent 中文回复")
    intent: str | None = Field(description="识别到的业务意图")
    missing_slots: list[str] = Field(description="仍需用户补充的槽位")
    tool_results_summary: dict = Field(description="工具调用结果摘要")
    handoff_required: bool = Field(description="是否需要转人工客服")


class ConversationSessionResponse(BaseModel):
    conversation_id: str = Field(description="服务端生成的会话编号")
    status: str = Field(description="会话状态")
    last_active_at: datetime = Field(description="最后成功对话时间")
    created_at: datetime = Field(description="创建时间")
