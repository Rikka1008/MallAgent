from pathlib import Path
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# pytest 会通过 pyproject 把 app/ 放入 pythonpath；而 uvicorn app.main:app 从项目根启动时，
# 默认只有项目根在导入路径中。这里显式补上 app/，保证两种启动方式都能使用同一套绝对导入。
app_dir = Path(__file__).resolve().parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from api.dependencies import close_dependencies, get_conversation_finalizer  # noqa: E402
from api.routes import router  # noqa: E402
from config import ConversationConfig, DatabaseConfig, MallConfig  # noqa: E402
from services.memory.checkpoint import checkpoint_manager  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ConversationConfig.validate()
    await checkpoint_manager.start()
    finalizer = None
    if DatabaseConfig.DATABASE_URL:
        finalizer = await get_conversation_finalizer()
        finalizer.start()
    try:
        yield
    finally:
        if finalizer is not None:
            await finalizer.stop()
        await checkpoint_manager.close()
        await close_dependencies()

app = FastAPI(title="电商售后智能客服 Agent", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=MallConfig.PORTAL_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)

web_dir = app_dir / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=web_dir), name="static")


@app.get("/")
def index():
    """返回 Web 演示页。"""
    return FileResponse(web_dir / "index.html")
