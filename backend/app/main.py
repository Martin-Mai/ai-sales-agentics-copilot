import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.api.chat import router as chat_router
from app.api.conversation import router as conversation_router
from app.api.upload import router as upload_router
from app.config import settings
from app.database.chroma_client import chroma_client
from app.database.mysql_client import engine, init_mysql

logger = logging.getLogger(__name__)

API_V1_PREFIX = "/api/v1"


def _error_response(detail: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "detail": detail},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_mysql()
    app.state.chroma_client = chroma_client
    yield
    await engine.dispose()
    chroma_client.close()
    app.state.chroma_client = None


app = FastAPI(
    title="AI Sales Agentics Copilot",
    description="销售智能助手 API — FastAPI + 异步 SQLAlchemy + ChromaDB + LangGraph SSE",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, str):
        detail = exc.detail
    else:
        detail = str(exc.detail)
    return _error_response(detail, exc.status_code)


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(
    _request: Request,
    exc: SQLAlchemyError,
) -> JSONResponse:
    logger.exception("数据库连接或操作异常")
    if isinstance(exc, DBAPIError) and exc.orig is not None:
        detail = f"数据库连接失败: {exc.orig}"
    else:
        detail = "数据库连接或操作失败，请稍后重试"
    return _error_response(detail, 503)


@app.exception_handler(Exception)
async def generic_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理的服务器异常")
    return _error_response(f"服务器内部错误: {exc}", 500)


app.include_router(upload_router, prefix=API_V1_PREFIX, tags=["Upload"])
app.include_router(conversation_router, prefix=API_V1_PREFIX, tags=["Conversation"])
app.include_router(chat_router, prefix=API_V1_PREFIX, tags=["Chat"])


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    return {
        "status": "ok",
        "model": settings.llm_model,
    }
