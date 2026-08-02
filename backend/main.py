from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from db_models import user, document, business

from api.chat import router
from api.upload import router as upload_router
from api.auth import router as auth_router
from api.register import router as register_router
from api.admin import router as admin_router
from database.mysql import Base, engine
from api.document import router as document_router
from api import session


Base.metadata.create_all(bind=engine)

# 前端目录
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="Enterprise RAG Assistant")

# CORS — 允许前端开发服务器跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载前端静态文件
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

app.include_router(auth_router)
app.include_router(document_router)
app.include_router(router)
app.include_router(upload_router)
app.include_router(register_router)
app.include_router(admin_router)
app.include_router(session.router)


@app.get("/")
async def root():
    """聊天界面入口"""
    chat_html = FRONTEND_DIR / "chat.html"
    if chat_html.exists():
        return FileResponse(chat_html)
    return {"message": "RAG Assistant Running"}