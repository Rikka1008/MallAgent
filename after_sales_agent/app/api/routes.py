import json
import logging
from collections.abc import AsyncIterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse

from adapters.ecommerce_gateway import EcommerceGateway
from agent.context import AgentRuntimeContext
from api.dependencies import (
    get_case_service,
    get_conversation_lifecycle,
    get_gateway,
    get_idempotency_store,
    get_main_agent,
    get_memory_store,
)
from api.schemas import (
    AuthSessionResponse,
    AuthenticatedUser,
    ChatRequest,
    ChatResponse,
    ConversationSessionResponse,
    MallLoginRequest,
)
from config import MallConfig
from domain.errors import AuthenticationError, PermissionDeniedError
from domain.models import UserMemory
from diagnostics.readiness import check_readiness
from services.chat_service import ChatService
from services.conversations.lifecycle import (
    ConversationBusyError,
    ConversationLifecycle,
    ConversationUnavailableError,
)
from services.conversations.models import ConversationTurn
from services.memory.stores import PostgresBaseStore

router = APIRouter()
logger = logging.getLogger("after_sales.api.routes")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _clear_auth_cookie(response: Response) -> None:
    """删除 Agent 域下的 Mall 会员 HttpOnly Cookie。"""

    response.delete_cookie(
        key="mall_access_token",
        path="/",
        secure=MallConfig.COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )


async def _build_context(
    request: ChatRequest,
    gateway: EcommerceGateway,
    memory_store: PostgresBaseStore,
    idempotency_store,
    case_service,
    conversation_lifecycle: ConversationLifecycle,
    member=None,
) -> AgentRuntimeContext:
    member = member or await gateway.get_current_member()
    item = await memory_store.get((member.user_id, "preferences"), "profile")
    memory = UserMemory(user_id=member.user_id, **item.value) if item else None
    case = await case_service.get_or_create(member.user_id, request.session_id)
    previous_conversations = await conversation_lifecycle.recall(member.user_id)
    return AgentRuntimeContext(
        user_id=member.user_id,
        session_id=request.session_id,
        gateway=gateway,
        case_context={"case": case},
        long_term_memory=memory,
        conversation_summaries=[
            item.summary_text for item in previous_conversations if item.summary_text
        ],
        idempotency_store=idempotency_store,
    )


async def _process_chat_turn(
    request: ChatRequest,
    main_agent,
    gateway: EcommerceGateway,
    memory_store: PostgresBaseStore,
    idempotency_store,
    case_service,
    conversation_lifecycle: ConversationLifecycle,
) -> ChatResponse:
    lease_token = None
    try:
        member = await gateway.get_current_member()
        lease_token = await conversation_lifecycle.begin_turn(
            request.session_id, member.user_id
        )
        context = await _build_context(
            request,
            gateway,
            memory_store,
            idempotency_store,
            case_service,
            conversation_lifecycle,
            member=member,
        )
        reply = await ChatService(main_agent).reply(
            request.message, request.session_id, context
        )
        try:
            await conversation_lifecycle.record_turn(
                request.session_id,
                member.user_id,
                ConversationTurn(user_text=request.message, assistant_text=reply),
            )
        except Exception:
            # Mall 写操作可能已经成功，不能因记忆持久化故障让前端误判并重放请求。
            logger.exception(
                "会话轮次持久化失败 conversation_id=%s user_id=%s",
                request.session_id,
                member.user_id,
            )
        return ChatResponse(
            session_id=request.session_id,
            reply=reply,
            intent=None,
            missing_slots=[],
            tool_results_summary={},
            handoff_required=False,
        )
    finally:
        if lease_token is not None:
            try:
                await conversation_lifecycle.release_turn(request.session_id, lease_token)
            except Exception:
                logger.warning(
                    "释放会话处理租约失败 conversation_id=%s",
                    request.session_id,
                )
        close = getattr(gateway, "close", None)
        if close is not None:
            await close()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.2.0"}


@router.get("/health/live")
def health_live() -> dict:
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready() -> JSONResponse:
    result = await check_readiness()
    status_code = status.HTTP_200_OK
    if any(item["status"] != "ok" for item in result.values()):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse({"services": result}, status_code=status_code)


@router.post("/api/auth/session", response_model=AuthSessionResponse)
async def create_auth_session(
    response: Response,
    authorization: str | None = Header(default=None),
    gateway: EcommerceGateway = Depends(get_gateway),
) -> AuthSessionResponse:
    """验证 Mall 会员令牌，并换取 Agent 域下的 HttpOnly Cookie。"""

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Mall 会员登录凭据。",
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Mall 会员登录凭据。",
        )

    member = await gateway.get_current_member()
    response.set_cookie(
        key="mall_access_token",
        value=token,
        httponly=True,
        secure=MallConfig.COOKIE_SECURE,
        samesite="lax",
        max_age=MallConfig.COOKIE_MAX_AGE_SECONDS,
    )
    return AuthSessionResponse(
        authenticated=True,
        user=AuthenticatedUser(user_id=member.user_id, username=member.username),
    )


@router.get("/api/auth/status", response_model=AuthSessionResponse)
async def get_auth_status(
    response: Response,
    mall_access_token: str | None = Cookie(default=None),
    gateway: EcommerceGateway = Depends(get_gateway),
) -> AuthSessionResponse:
    """检查 Agent 域下的会员 Cookie 是否仍可通过 Mall 身份校验。"""

    if not mall_access_token:
        return AuthSessionResponse(authenticated=False)
    try:
        member = await gateway.get_current_member()
    except AuthenticationError:
        _clear_auth_cookie(response)
        return AuthSessionResponse(authenticated=False)
    return AuthSessionResponse(
        authenticated=True,
        user=AuthenticatedUser(user_id=member.user_id, username=member.username),
    )


@router.get("/api/auth/mall-login", response_class=RedirectResponse)
def redirect_to_mall_login() -> RedirectResponse:
    """跳转到 Mall 会员登录页，并携带非敏感的 Agent 回跳地址。"""

    login_url = urlsplit(MallConfig.LOGIN_URL)
    query = dict(parse_qsl(login_url.query, keep_blank_values=True))
    query["agent_base_url"] = MallConfig.AGENT_PUBLIC_URL.rstrip("/")
    target = urlunsplit(login_url._replace(query=urlencode(query)))
    return RedirectResponse(target)


@router.post("/api/auth/logout", response_model=AuthSessionResponse)
def logout(response: Response) -> AuthSessionResponse:
    """退出 Agent 会员会话，不修改 Mall 门户或用户长期记忆。"""

    _clear_auth_cookie(response)
    return AuthSessionResponse(authenticated=False)


def _conversation_response(conversation) -> ConversationSessionResponse:
    return ConversationSessionResponse(
        conversation_id=conversation.conversation_id,
        status=conversation.status.value,
        last_active_at=conversation.last_active_at,
        created_at=conversation.created_at,
    )


@router.get("/api/conversations/active", response_model=ConversationSessionResponse)
async def get_active_conversation(
    gateway: EcommerceGateway = Depends(get_gateway),
    lifecycle: ConversationLifecycle = Depends(get_conversation_lifecycle),
) -> ConversationSessionResponse:
    member = await gateway.get_current_member()
    conversation = await lifecycle.get_active(member.user_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有可续接的会话。")
    return _conversation_response(conversation)


@router.post(
    "/api/conversations",
    response_model=ConversationSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    gateway: EcommerceGateway = Depends(get_gateway),
    lifecycle: ConversationLifecycle = Depends(get_conversation_lifecycle),
) -> ConversationSessionResponse:
    member = await gateway.get_current_member()
    try:
        conversation = await lifecycle.create_new(member.user_id)
    except ConversationBusyError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _conversation_response(conversation)


@router.post("/api/auth/login")
async def login_to_mall(request: MallLoginRequest) -> JSONResponse:
    try:
        async with httpx.AsyncClient(
            timeout=MallConfig.REQUEST_TIMEOUT_SECONDS, trust_env=False
        ) as client:
            mall_response = await client.post(
                f"{MallConfig.PORTAL_BASE_URL.rstrip('/')}/sso/login",
                data={"username": request.username, "password": request.password},
            )
        payload = mall_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Mall 登录服务暂时不可用，请稍后重试。",
        ) from exc

    token = (payload.get("data") or {}).get("token") if isinstance(payload, dict) else None
    if mall_response.status_code != status.HTTP_200_OK or payload.get("code") != 200 or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=payload.get("message") or "用户名或密码错误。",
        )
    response = JSONResponse({"message": "登录成功"})
    response.set_cookie("mall_access_token", token, httponly=True, samesite="lax")
    return response


@router.post("/api/chat/stream")
async def chat_stream(
    request: ChatRequest,
    main_agent=Depends(get_main_agent),
    gateway: EcommerceGateway = Depends(get_gateway),
    memory_store: PostgresBaseStore = Depends(get_memory_store),
    idempotency_store=Depends(get_idempotency_store),
    case_service=Depends(get_case_service),
    conversation_lifecycle: ConversationLifecycle = Depends(get_conversation_lifecycle),
) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        yield _sse("message_start", {"session_id": request.session_id})
        try:
            response = await _process_chat_turn(
                request,
                main_agent,
                gateway,
                memory_store,
                idempotency_store,
                case_service,
                conversation_lifecycle,
            )
            yield _sse("message_delta", {"delta": response.reply})
            yield _sse("message_end", response.model_dump(exclude={"reply"}))
        except AuthenticationError as exc:
            yield _sse("error", {"status": 401, "detail": str(exc)})
        except PermissionDeniedError as exc:
            yield _sse("error", {"status": 403, "detail": str(exc)})
        except ConversationUnavailableError as exc:
            yield _sse(
                "error",
                {"status": 409, "code": "conversation_expired", "detail": str(exc)},
            )
        except ConversationBusyError as exc:
            yield _sse(
                "error",
                {"status": 409, "code": "conversation_busy", "detail": str(exc)},
            )
        except Exception:
            logger.exception("聊天流处理失败 conversation_id=%s", request.session_id)
            yield _sse(
                "error",
                {"status": 500, "detail": "服务暂时不可用，请稍后重试。"},
            )

    return StreamingResponse(events(), media_type="text/event-stream")
