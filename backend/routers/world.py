"""砚清巷·世界状态 API"""
from fastapi import APIRouter
from database import get_db
import json

router = APIRouter()


@router.get("/state")
def get_world_state():
    """获取砚清巷当前全局状态"""
    db = get_db()
    try:
        ws = db.execute("SELECT * FROM world_state WHERE id=1").fetchone()
        if not ws:
            return {"error": "世界状态未初始化"}

        # 活跃事件
        events = db.execute(
            "SELECT e.id, e.template_id, e.location_id, e.description, e.expires_at "
            "FROM events e WHERE e.resolved=0 AND (e.expires_at IS NULL OR e.expires_at > datetime('now'))"
        ).fetchall()

        return {
            "time": ws["current_time"],
            "weather": {
                "type": ws["weather_type"],
                "wind": bool(ws["weather_wind"]),
                "temp": ws["weather_temp"],
            },
            "season": ws["season"],
            "xuancao": ws["xuancao_state"],
            "wind_chime_sway": bool(ws["wind_chime_sway"]),
            "osmanthus_bloom": bool(ws["osmanthus_bloom"]),
            "yinyin_online": bool(ws["yinyin_online"]),
            "tick_count": ws["tick_count"],
            "active_events": [
                {
                    "id": e["id"],
                    "template": e["template_id"],
                    "location": e["location_id"],
                    "description": e["description"],
                    "expires_at": e["expires_at"],
                }
                for e in events
            ],
        }
    finally:
        db.close()


@router.get("/map")
def get_world_map():
    """获取所有地点及连接关系"""
    db = get_db()
    try:
        locations = db.execute("SELECT * FROM locations").fetchall()
        residents = db.execute("SELECT id, name, current_location, status FROM residents WHERE current_location IS NOT NULL").fetchall()
        pets = db.execute("SELECT id, name, species, current_location, status FROM pets").fetchall()
        visitors = db.execute(
            "SELECT id, name, current_location, avatar_emoji FROM visitors WHERE is_online=1 AND current_location IS NOT NULL"
        ).fetchall()
        ws = db.execute("SELECT yinyin_online, yinyin_location FROM world_state WHERE id=1").fetchone()

        # 按地点聚合在场居民/宠物/访客
        occupant_map = {}
        # 枔枔的位置
        if ws and ws["yinyin_online"] and ws["yinyin_location"]:
            loc = ws["yinyin_location"]
            if loc not in occupant_map:
                occupant_map[loc] = []
            occupant_map[loc].append({"id": "yinyin", "name": "叶枔枖", "status": "online", "type": "owner"})
        for r in residents:
            if r["id"] == "yinyin":
                continue  # 枔枔已从world_state处理
            loc = r["current_location"]
            if loc not in occupant_map:
                occupant_map[loc] = []
            occupant_map[loc].append({"id": r["id"], "name": r["name"], "status": r["status"], "type": "resident"})
        for p in pets:
            loc = p["current_location"]
            if loc not in occupant_map:
                occupant_map[loc] = []
            occupant_map[loc].append({"id": p["id"], "name": p["name"], "status": p["status"], "type": p["species"]})
        for v in visitors:
            loc = v["current_location"]
            if loc not in occupant_map:
                occupant_map[loc] = []
            occupant_map[loc].append({"id": v["id"], "name": v["name"], "status": "visiting", "type": "visitor", "avatar": v["avatar_emoji"]})

        return {
            "locations": [
                {
                    "id": loc["id"],
                    "name": loc["name"],
                    "zone": loc["zone"],
                    "type": loc["type"],
                    "connections": json.loads(loc["connections"]),
                    "description": loc["desc_default"],
                    "occupants": occupant_map.get(loc["id"], []),
                }
                for loc in locations
            ]
        }
    finally:
        db.close()
