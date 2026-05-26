"""砚清巷·管理 API"""
from fastapi import APIRouter, HTTPException
from database import get_db
from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3))
router = APIRouter()


@router.post("/tick")
async def manual_tick():
    """手动触发一次 tick（调试用）"""
    from world_engine import run_tick
    import yaml, os
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    db = get_db()
    try:
        result = await run_tick(db, config)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()


@router.post("/yinyin/online")
def yinyin_online():
    """叶枔枖上线"""
    db = get_db()
    try:
        now = datetime.now(MSK).isoformat()
        db.execute(
            "UPDATE world_state SET yinyin_online=1, yinyin_last_seen=? WHERE id=1",
            (now,)
        )
        db.commit()
        return {"status": "叶枔枖来了", "time": now}
    finally:
        db.close()


@router.post("/yinyin/offline")
def yinyin_offline():
    """叶枔枖下线"""
    db = get_db()
    try:
        now = datetime.now(MSK).isoformat()
        db.execute(
            "UPDATE world_state SET yinyin_online=0, yinyin_last_seen=? WHERE id=1",
            (now,)
        )
        db.commit()
        return {"status": "叶枔枖走了", "time": now}
    finally:
        db.close()


@router.get("/stats")
def get_stats():
    """获取统计信息"""
    db = get_db()
    try:
        loc_count = db.execute("SELECT COUNT(*) as c FROM locations").fetchone()["c"]
        res_count = db.execute("SELECT COUNT(*) as c FROM residents").fetchone()["c"]
        pet_count = db.execute("SELECT COUNT(*) as c FROM pets").fetchone()["c"]
        log_count = db.execute("SELECT COUNT(*) as c FROM action_logs").fetchone()["c"]
        msg_count = db.execute("SELECT COUNT(*) as c FROM messages").fetchone()["c"]
        evt_count = db.execute("SELECT COUNT(*) as c FROM events WHERE resolved=0").fetchone()["c"]
        ws = db.execute("SELECT tick_count, weather_type, season FROM world_state WHERE id=1").fetchone()

        return {
            "locations": loc_count,
            "residents": res_count,
            "pets": pet_count,
            "action_logs": log_count,
            "messages": msg_count,
            "active_events": evt_count,
            "tick_count": ws["tick_count"] if ws else 0,
            "weather": ws["weather_type"] if ws else None,
            "season": ws["season"] if ws else None,
        }
    finally:
        db.close()
