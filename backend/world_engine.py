"""砚清巷·世界引擎 tick 循环"""
import json
import random
from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3))


async def run_tick(db, config):
    """
    执行一次世界 tick。

    流程：
    1. 更新世界时间
    2. 检查萱草开合
    3. 检查事件触发
    4. 清理过期事件和临时权限
    5. (TODO) 调用砚清模型
    6. (TODO) 调用克宝模型
    7. 处理宠物移动
    8. 更新 tick 计数
    """
    now = datetime.now(MSK)
    hour = now.hour

    # ── 1. 更新世界时间 ──
    db.execute("UPDATE world_state SET current_time=? WHERE id=1", (now.isoformat(),))

    # ── 2. 萱草开合 ──
    xuancao = "open" if 6 <= hour < 20 else "closed"
    db.execute("UPDATE world_state SET xuancao_state=? WHERE id=1", (xuancao,))

    # ── 3. 检查季节 ──
    month = now.month
    if month in (3, 4, 5):
        season = "spring"
    elif month in (6, 7, 8):
        season = "summer"
    elif month in (9, 10, 11):
        season = "autumn"
    else:
        season = "winter"
    osmanthus = 1 if season == "autumn" else 0
    db.execute("UPDATE world_state SET season=?, osmanthus_bloom=? WHERE id=1", (season, osmanthus))

    # ── 4. 检查事件模板触发 ──
    triggered_events = _check_event_triggers(db, now)

    # ── 5. 清理过期事件 ──
    db.execute(
        "UPDATE events SET resolved=1 WHERE resolved=0 AND expires_at IS NOT NULL AND expires_at < ?",
        (now.isoformat(),)
    )

    # ── 6. 清理过期临时权限 ──
    db.execute(
        "DELETE FROM permissions WHERE is_temporary=1 AND expires_at IS NOT NULL AND expires_at < ?",
        (now.isoformat(),)
    )

    # ── 7. 宠物移动 ──
    pet_moves = _move_pets(db)

    # ── 8. TODO: 调用 AI 模型 ──
    # 砚清行为决策
    # 克宝行为决策
    # 这部分等模型调用层写好再接入

    # ── 9. 更新 tick 计数 ──
    ws = db.execute("SELECT tick_count FROM world_state WHERE id=1").fetchone()
    tick_number = ws["tick_count"] + 1
    db.execute(
        "UPDATE world_state SET tick_count=?, last_tick_at=? WHERE id=1",
        (tick_number, now.isoformat())
    )

    db.commit()

    return {
        "tick_number": tick_number,
        "time": now.isoformat(),
        "xuancao": xuancao,
        "season": season,
        "events_triggered": triggered_events,
        "pet_moves": pet_moves,
        "ai_actions": [],  # TODO
    }


def _check_event_triggers(db, now):
    """检查事件模板，满足条件的按概率触发"""
    templates = db.execute("SELECT * FROM event_templates").fetchall()
    ws = db.execute("SELECT * FROM world_state WHERE id=1").fetchone()
    triggered = []

    hour = now.hour
    hour_str = f"{hour:02d}:00"

    for t in templates:
        conditions = json.loads(t["conditions"]) if t["conditions"] else {}

        # 检查条件
        match = True
        for key, val in conditions.items():
            if key == "weather" and ws["weather_type"] != val:
                match = False
            elif key == "weather_wind" and bool(ws["weather_wind"]) != val:
                match = False
            elif key == "season" and ws["season"] != val:
                match = False
            elif key == "yinyin_online" and bool(ws["yinyin_online"]) != val:
                match = False
            elif key == "time_range":
                start, end = val.split("-")
                sh, sm = map(int, start.split(":"))
                eh, em = map(int, end.split(":"))
                start_min = sh * 60 + sm
                end_min = eh * 60 + em
                now_min = now.hour * 60 + now.minute
                if start_min <= end_min:
                    if not (start_min <= now_min <= end_min):
                        match = False
                else:  # 跨午夜
                    if not (now_min >= start_min or now_min <= end_min):
                        match = False

        if not match:
            continue

        # 概率检查
        if random.random() > t["probability"]:
            continue

        # 检查冷却
        if t["cooldown_minutes"] > 0:
            last = db.execute(
                "SELECT MAX(started_at) as last_at FROM events WHERE template_id=?",
                (t["id"],)
            ).fetchone()
            if last and last["last_at"]:
                # 简单冷却检查
                pass  # TODO: 精确冷却时间比较

        # 触发事件
        expires_at = None
        if t["duration_minutes"]:
            expires_at = (now + timedelta(minutes=t["duration_minutes"])).isoformat()

        db.execute(
            "INSERT INTO events (template_id, location_id, description, expires_at) VALUES (?,?,?,?)",
            (t["id"], t["location_id"], t["description_template"], expires_at)
        )
        triggered.append({"template": t["id"], "description": t["description_template"]})

    return triggered


def _move_pets(db):
    """处理宠物移动"""
    pets = db.execute("SELECT * FROM pets").fetchall()
    moves = []

    for pet in pets:
        if pet["behavior_pattern"] == "follow_owner" and pet["follow_target"]:
            # 拉波跟着砚清
            owner = db.execute(
                "SELECT current_location FROM residents WHERE id=?",
                (pet["follow_target"],)
            ).fetchone()
            if owner and owner["current_location"] != pet["current_location"]:
                # 70%概率跟过去（不是每次都跟）
                if random.random() < 0.7:
                    old_loc = pet["current_location"]
                    new_loc = owner["current_location"]
                    db.execute(
                        "UPDATE pets SET current_location=? WHERE id=?",
                        (new_loc, pet["id"])
                    )
                    moves.append({"pet": pet["name"], "from": old_loc, "to": new_loc, "reason": "跟着主人"})

        elif pet["behavior_pattern"] == "independent":
            # 拉哈按权重随机漫游（30%概率移动）
            if random.random() < 0.3:
                weights = json.loads(pet["location_weights"]) if pet["location_weights"] else {}
                if weights:
                    locations = list(weights.keys())
                    probs = list(weights.values())
                    total = sum(probs)
                    probs = [p / total for p in probs]
                    new_loc = random.choices(locations, weights=probs, k=1)[0]
                    if new_loc != pet["current_location"]:
                        old_loc = pet["current_location"]
                        db.execute(
                            "UPDATE pets SET current_location=? WHERE id=?",
                            (new_loc, pet["id"])
                        )
                        moves.append({"pet": pet["name"], "from": old_loc, "to": new_loc, "reason": "自由漫游"})

    return moves
