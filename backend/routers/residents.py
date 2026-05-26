"""砚清巷·居民 API"""
from fastapi import APIRouter, HTTPException
from database import get_db
import json

router = APIRouter()


@router.get("")
def get_all_residents():
    """获取所有居民和宠物当前状态"""
    db = get_db()
    try:
        residents = db.execute(
            "SELECT id, name, type, current_location, current_floor, status, mood, last_action_at FROM residents"
        ).fetchall()
        pets = db.execute(
            "SELECT id, name, species, current_location, status, behavior_pattern, follow_target FROM pets"
        ).fetchall()

        return {
            "residents": [dict(r) for r in residents],
            "pets": [dict(p) for p in pets],
        }
    finally:
        db.close()


@router.get("/{resident_id}")
def get_resident(resident_id: str):
    """获取单个居民详细状态"""
    db = get_db()
    try:
        r = db.execute("SELECT * FROM residents WHERE id=?", (resident_id,)).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail=f"居民 {resident_id} 不存在")
        result = dict(r)
        if result.get("daily_routine"):
            result["daily_routine"] = json.loads(result["daily_routine"])
        return result
    finally:
        db.close()


@router.get("/{resident_id}/history")
def get_resident_history(resident_id: str, hours: int = 24, limit: int = 50):
    """获取居民近期行为日志"""
    db = get_db()
    try:
        r = db.execute("SELECT id FROM residents WHERE id=?", (resident_id,)).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail=f"居民 {resident_id} 不存在")

        actions = db.execute(
            "SELECT tick_number, created_at, action_type, from_location, to_location, detail, mood_before, mood_after "
            "FROM action_logs WHERE resident_id=? AND created_at > datetime('now', ? || ' hours') "
            "ORDER BY created_at DESC LIMIT ?",
            (resident_id, f"-{hours}", limit)
        ).fetchall()

        return {
            "resident": resident_id,
            "period": f"last_{hours}h",
            "actions": [dict(a) for a in actions],
        }
    finally:
        db.close()


@router.post("/{resident_id}/update")
def update_resident(resident_id: str, data: dict):
    """更新居民状态（砚清巷插件调用）"""
    db = get_db()
    try:
        r = db.execute("SELECT * FROM residents WHERE id=?", (resident_id,)).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail=f"居民 {resident_id} 不存在")

        old_location = r["current_location"]
        old_mood = r["mood"]

        new_location = data.get("current_location", old_location)
        new_status = data.get("status", r["status"])
        new_mood = data.get("mood", old_mood)

        db.execute(
            "UPDATE residents SET current_location=?, status=?, mood=?, last_action_at=datetime('now') WHERE id=?",
            (new_location, new_status, new_mood, resident_id)
        )

        # 写行为日志
        action_type = "move" if new_location != old_location else "interact"
        ws = db.execute("SELECT tick_count FROM world_state WHERE id=1").fetchone()
        db.execute(
            "INSERT INTO action_logs (resident_id, tick_number, action_type, from_location, to_location, detail, mood_before, mood_after) VALUES (?,?,?,?,?,?,?,?)",
            (resident_id, ws["tick_count"] if ws else 0, action_type, old_location, new_location, new_status, old_mood, new_mood)
        )

        db.commit()
        return {"updated": True, "location": new_location, "status": new_status, "mood": new_mood}
    finally:
        db.close()
