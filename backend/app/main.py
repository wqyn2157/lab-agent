import asyncio
from contextlib import asynccontextmanager
import traceback

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from app import api
from app.config import UPLOAD_DIR
from app.models.user import User
from app.models.lab import Lab
from app.models.reservation import Reservation
from app.database import engine, Base
from app.api import api
from app.common.exceptions import (
    BusinessException,
    bussiness_exception_hadler,
    http_exception_hadler,
    validation_exception_hadler,
    global_exception_hadler,
)
from app.services import kb_service, reservation_service

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await asyncio.to_thread(kb_service.warmup)
    except Exception:
        traceback.print_exc()
    # 启动项目开启异步的扫描任务
    task = asyncio.create_task(reservation_service.run_expire_scan())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)

origins = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 允许的前端源，不要直接写 ["*"]
    allow_credentials=True,  # ✅ 关键：允许前端携带 Authorization token
    allow_methods=["*"],  # 允许所有请求方法 GET POST PUT DELETE OPTIONS
    allow_headers=["*"],  # 允许所有请求头（包含Authorization）
)

app.include_router(api)

# 注册异常处理期
app.add_exception_handler(BusinessException, bussiness_exception_hadler)
app.add_exception_handler(HTTPException, http_exception_hadler)
app.add_exception_handler(RequestValidationError, validation_exception_hadler)
# 全局异常兜底，必须放在最后注册
app.add_exception_handler(Exception, global_exception_hadler)


# 挂载静态的文件访问目录 http://127.0.0.1:8000/uploads/xxx.jpg
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/")
def root():
    return {"message": "FastAPI 工程正在运行中"}
