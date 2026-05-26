"""砚清巷·世界引擎"""
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import yaml
import os

from database import init_db, get_db
from routers import world, residents, admin


# ── 加载配置 ──
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


config = load_config()
scheduler = AsyncIOScheduler(timezone=config["world"]["timezone"])


# ── 生命周期 ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    init_db()
    tick_minutes = config["world"]["tick_interval_minutes"]
    scheduler.add_job(tick_loop, "interval", minutes=tick_minutes, id="world_tick")
    scheduler.start()
    print(f"🏘️ 砚清巷启动 | tick间隔: {tick_minutes}分钟")
    yield
    # 关闭
    scheduler.shutdown()
    print("🌙 砚清巷关闭")


async def tick_loop():
    """世界引擎主循环——每15分钟执行一次"""
    from world_engine import run_tick
    db = get_db()
    try:
        result = await run_tick(db, config)
        print(f"⏱️ tick #{result['tick_number']} 完成")
    except Exception as e:
        print(f"❌ tick 失败: {e}")
    finally:
        db.close()


# ── FastAPI 实例 ──
app = FastAPI(
    title="砚清巷",
    description="砚清巷·世界引擎 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ──
app.include_router(world.router, prefix="/api/v1/world", tags=["世界"])
app.include_router(residents.router, prefix="/api/v1/residents", tags=["居民"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["管理"])


@app.get("/")
def root():
    return {
        "name": "砚清巷",
        "version": "0.1.0",
        "status": "running",
        "motto": "砚清是名字。巷是家的尺度。不大不空。走几步就到。"
    }


@app.get("/health")
def health():
    db = get_db()
    try:
        tick = db.execute("SELECT tick_count FROM world_state WHERE id=1").fetchone()
        return {"status": "ok", "tick_count": tick["tick_count"] if tick else 0}
    finally:
        db.close()
