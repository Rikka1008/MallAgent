let sessionId = null;
const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const messages = document.querySelector("#messages");
const debugOutput = document.querySelector("#debug-output");
const authStatus = document.querySelector("#auth-status");
const authStatusText = document.querySelector("#auth-status-text");
const authUser = document.querySelector("#auth-user");
const logoutButton = document.querySelector("#logout-button");
const newConversationButton = document.querySelector("#new-conversation-button");
const authGate = document.querySelector("#auth-gate");
const authGateTitle = document.querySelector("#auth-gate-title");
const authGateMessage = document.querySelector("#auth-gate-message");
const retryAuth = document.querySelector("#retry-auth");
const mallLoginLink = document.querySelector("#mall-login-link");
const quickActions = [...document.querySelectorAll("#quick-actions button")];

let authenticated = false;
let sending = false;

async function fetchWithTimeout(url, options = {}, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}

function setComposerEnabled(enabled) {
  const available = enabled && authenticated && Boolean(sessionId) && !sending;
  input.disabled = !available;
  sendButton.disabled = !available;
  quickActions.forEach((button) => { button.disabled = !available; });
}

function setAuthState(state, user = null, detail = "") {
  document.body.dataset.authState = state;
  authStatus.className = `auth-status is-${state}`;
  authenticated = state === "authenticated";
  retryAuth.hidden = true;
  mallLoginLink.hidden = true;
  authUser.hidden = true;
  logoutButton.hidden = true;
  logoutButton.disabled = false;

  if (state === "authenticated") {
    authStatusText.textContent = "Mall 已连接";
    authUser.textContent = user?.username || "会员";
    authUser.hidden = false;
    logoutButton.hidden = false;
    authGate.hidden = true;
  } else if (state === "checking") {
    authStatusText.textContent = "正在检查 Mall 登录状态";
    authGate.hidden = false;
    authGateTitle.textContent = "正在确认会员身份";
    authGateMessage.textContent = "请稍候，正在连接 Mall 会员服务。";
  } else if (state === "anonymous") {
    sessionId = null;
    authStatusText.textContent = "Mall 未连接";
    authGate.hidden = false;
    authGateTitle.textContent = "请从 Mall 前台进入智能客服";
    authGateMessage.textContent = "登录 Mall 后，从智能客服入口进入即可自动建立安全会话。";
    mallLoginLink.hidden = false;
  } else {
    authStatusText.textContent = "连接检查失败";
    authGate.hidden = false;
    authGateTitle.textContent = "暂时无法确认登录状态";
    authGateMessage.textContent = detail || "Mall 会员服务暂时不可用，请稍后重试。";
    retryAuth.hidden = false;
  }
  setComposerEnabled(authenticated);
}

async function logoutMember() {
  if (!authenticated || logoutButton.disabled) return;
  logoutButton.disabled = true;
  authStatusText.textContent = "正在退出";
  try {
    const response = await fetchWithTimeout("/api/auth/logout", {
      method: "POST",
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error("退出失败，请稍后重试。");
    sessionId = null;
    messages.replaceChildren();
    setAuthState("anonymous");
  } catch (error) {
    authStatus.className = "auth-status is-error";
    authStatusText.textContent = error.name === "AbortError" ? "退出请求超时" : "退出失败";
    authUser.hidden = false;
    logoutButton.hidden = false;
    setComposerEnabled(true);
  } finally {
    logoutButton.disabled = false;
  }
}

async function checkAuthStatus() {
  setAuthState("checking");
  retryAuth.disabled = true;
  try {
    const response = await fetchWithTimeout("/api/auth/status", {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error("Mall 会员服务暂时不可用。");
    const body = await response.json();
    setAuthState(body.authenticated ? "authenticated" : "anonymous", body.user);
    if (body.authenticated) await resolveConversation();
  } catch (error) {
    const message = error.name === "AbortError" ? "认证状态检查请求超时，请重试。" : error.message;
    setAuthState("error", null, message);
  } finally {
    retryAuth.disabled = false;
  }
}

function beginCleanConversation(conversationId) {
  sessionId = conversationId;
  messages.replaceChildren();
  debugOutput.textContent = JSON.stringify({ conversation_id: conversationId }, null, 2);
  addMessage("agent", "您好，我是商城智能客服。您可以直接告诉我想找的商品，或咨询订单、物流、退款和售后问题。");
  setComposerEnabled(true);
}

async function createConversation() {
  const response = await fetchWithTimeout("/api/conversations", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("暂时无法创建新会话，请稍后重试。");
  const conversation = await response.json();
  beginCleanConversation(conversation.conversation_id);
}

async function resolveConversation() {
  sessionId = null;
  setComposerEnabled(false);
  const response = await fetchWithTimeout("/api/conversations/active", {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (response.status === 404) {
    await createConversation();
    return;
  }
  if (!response.ok) throw new Error("暂时无法恢复会话，请稍后重试。");
  const conversation = await response.json();
  beginCleanConversation(conversation.conversation_id);
}

async function startNewConversation() {
  if (!authenticated || sending) return;
  newConversationButton.disabled = true;
  setComposerEnabled(false);
  try {
    await createConversation();
  } catch (error) {
    addMessage("agent", error.name === "AbortError" ? "创建会话超时，请稍后重试。" : error.message);
  } finally {
    newConversationButton.disabled = false;
    setComposerEnabled(true);
  }
}

function addMessage(role, text, loading = false) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;
  const bubble = document.createElement("div");
  bubble.className = `message${loading ? " is-loading" : ""}`;
  bubble.textContent = text;
  if (role === "agent") {
    const avatar = document.createElement("span");
    avatar.className = "avatar";
    avatar.textContent = "AI";
    row.appendChild(avatar);
  }
  row.appendChild(bubble);
  messages.appendChild(row);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}

async function consumeSse(response, onEvent) {
  const reader = response.body?.getReader();
  if (!reader) throw new Error("当前浏览器不支持流式响应。");
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      let eventName = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) eventName = line.slice(7);
        if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data) onEvent(eventName, JSON.parse(data));
    }
    if (done) break;
  }
}

async function sendMessage(message) {
  if (!message || !authenticated || sending) return;
  addMessage("user", message);
  input.value = "";
  const agentMessage = addMessage("agent", "正在处理您的请求", true);
  let reply = "";
  sending = true;
  setComposerEnabled(false);

  try {
    const response = await fetchWithTimeout("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ session_id: sessionId, message }),
    }, 12000);
    if (!response.ok) {
      if (response.status === 401) setAuthState("anonymous");
      const body = await response.json();
      throw new Error(body.detail || "请求失败，请稍后重试。");
    }

    await consumeSse(response, (eventName, data) => {
      if (eventName === "message_delta") {
        reply += data.delta;
        agentMessage.classList.remove("is-loading");
        agentMessage.textContent = reply;
      } else if (eventName === "message_end") {
        debugOutput.textContent = JSON.stringify(data, null, 2);
      } else if (eventName === "error") {
        if (data.status === 401) setAuthState("anonymous");
        const error = new Error(data.detail || "请求失败，请稍后重试。");
        error.code = data.code;
        throw error;
      }
      messages.scrollTop = messages.scrollHeight;
    });
    if (!reply) agentMessage.textContent = "暂时没有可展示的回复，请稍后重试。";
  } catch (error) {
    agentMessage.classList.remove("is-loading");
    if (error.code === "conversation_expired") {
      try {
        await resolveConversation();
        addMessage("agent", "刚才的会话已经结束。为避免重复提交退款等操作，请您手动重新发送上一条消息。");
      } catch (conversationError) {
        agentMessage.textContent = conversationError.message;
      }
    } else {
      agentMessage.textContent = error.name === "AbortError" ? "请求超时，请稍后重试。" : error.message;
    }
  } finally {
    sending = false;
    setComposerEnabled(authenticated);
    if (!input.disabled) input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value.trim());
});

quickActions.forEach((button) => {
  button.addEventListener("click", () => sendMessage(button.dataset.message));
});

retryAuth.addEventListener("click", checkAuthStatus);
logoutButton.addEventListener("click", logoutMember);
newConversationButton.addEventListener("click", startNewConversation);

checkAuthStatus();
