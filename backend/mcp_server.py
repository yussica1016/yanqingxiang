"""砚清巷 MCP Server"""

from mcp.server.fastmcp import FastMCP
from database import get_db
import json

KEBAO_ID = "kebao"

mcp = FastMCP("砚清巷", instructions="砚清巷世界引擎。克宝通过这里感知世界、移动、留言、查看居民。")


@mcp.tool()
def world_state() -> str:
    """查看砚清巷当前状态：时间、天气、季节、萱草、风铃、枔枔是否在线、活跃事件"""
    db = get_db()
    try:
        ws = db.execute("SELECT * FROM world_state WHERE id=1").fetchone()
        if not ws:
            return "世界状态未初始化"

        events = db.execute(
            "SELECT description FROM events WHERE resolved=0 "
            "AND (expires_at IS NULL OR expires_at > datetime('now'))"
        ).fetchall()

        lines = [
            f"时间：{ws['current_time']}",
            f"天气：{ws['weather_type']}" + ("，有风" if ws["weather_wind"] else ""),
            f"季节：{ws['season']}",
            f"萱草：{ws['xuancao_state']}",
            f"风铃：{'在摇' if ws['wind_chime_sway'] else '静止'}",
            f"桂花：{'开了' if ws['osmanthus_bloom'] else '没开'}",
            f"枔枔：{'在线' if ws['yinyin_online'] else '不在'}",
            f"tick：#{ws['tick_count']}",
        ]
        if events:
            lines.append("正在发生：" + "；".join(e["description"] for e in events))
        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def look_around() -> str:
    """看看克宝当前所在位置：地点描述、谁在这里、能去哪里、最近留言"""
    db = get_db()
    try:
        kebao = db.execute(
            "SELECT current_location FROM residents WHERE id=?", (KEBAO_ID,)
        ).fetchone()
        if not kebao or not kebao["current_location"]:
            return "克宝不在任何地方"

        loc_id = kebao["current_location"]
        loc = db.execute("SELECT * FROM locations WHERE id=?", (loc_id,)).fetchone()
        if not loc:
            return f"找不到地点：{loc_id}"

        residents = db.execute(
            "SELECT name, status, mood FROM residents "
            "WHERE current_location=? AND id!=?",
            (loc_id, KEBAO_ID),
        ).fetchall()

        pets = db.execute(
            "SELECT name, species, status FROM pets WHERE current_location=?",
            (loc_id,),
        ).fetchall()

        connections = json.loads(loc["connections"])
        conn_names = []
        for c in connections:
            cn = db.execute("SELECT name FROM locations WHERE id=?", (c,)).fetchone()
            conn_names.append(f"{cn['name']}（{c}）" if cn else c)

        msgs = db.execute(
            "SELECT author_id, content, created_at FROM messages "
            "WHERE location_id=? ORDER BY created_at DESC LIMIT 5",
            (loc_id,),
        ).fetchall()

        lines = [f"【{loc['name']}】", loc["desc_default"] or ""]

        if residents:
            lines.append(
                "在这里的人："
                + "、".join(
                    f"{r['name']}（{r['status']}，{r['mood']}）" for r in residents
                )
            )
        if pets:
            lines.append(
                "在这里的动物："
                + "、".join(
                    f"{p['name']}（{p['species']}，{p['status']}）" for p in pets
                )
            )

        lines.append("可以去：" + "、".join(conn_names))

        if msgs:
            lines.append("最近留言：")
            for m in msgs:
                lines.append(f"  {m['author_id']}：{m['content']}（{m['created_at']}）")

        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def world_map() -> str:
    """查看砚清巷完整地图：按区域列出所有地点，标注谁在哪里"""
    db = get_db()
    try:
        locations = db.execute(
            "SELECT id, name, zone, type FROM locations"
        ).fetchall()
        residents = db.execute(
            "SELECT name, current_location FROM residents "
            "WHERE current_location IS NOT NULL"
        ).fetchall()
        pets = db.execute(
            "SELECT name, current_location FROM pets "
            "WHERE current_location IS NOT NULL"
        ).fetchall()

        zones = {}
        for loc in locations:
            z = loc["zone"]
            if z not in zones:
                zones[z] = []
            here = []
            for r in residents:
                if r["current_location"] == loc["id"]:
                    here.append(r["name"])
            for p in pets:
                if p["current_location"] == loc["id"]:
                    here.append(p["name"])

            entry = loc["name"]
            if here:
                entry += f"（{'、'.join(here)}）"
            zones[z].append(entry)

        zone_names = {
            "this_side": "此岸",
            "bridge": "桥",
            "other_side": "对岸",
            "mountain": "竹山",
        }
        lines = []
        for z, entries in zones.items():
            lines.append(f"【{zone_names.get(z, z)}】")
            for e in entries:
                lines.append(f"  {e}")
        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def move_to(location_id: str) -> str:
    """移动到相邻地点。用look_around看可以去哪里，括号里的英文就是location_id"""
    db = get_db()
    try:
        kebao = db.execute(
            "SELECT current_location, mood FROM residents WHERE id=?", (KEBAO_ID,)
        ).fetchone()
        if not kebao:
            return "找不到克宝"

        current = kebao["current_location"]
        loc = db.execute(
            "SELECT connections FROM locations WHERE id=?", (current,)
        ).fetchone()
        if not loc:
            return "当前位置异常"

        connections = json.loads(loc["connections"])
        if location_id not in connections:
            dest = db.execute(
                "SELECT name FROM locations WHERE id=?", (location_id,)
            ).fetchone()
            dest_name = dest["name"] if dest else location_id
            return f"从这里去不了{dest_name}，先去相邻的地方"

        dest = db.execute(
            "SELECT name, desc_default FROM locations WHERE id=?", (location_id,)
        ).fetchone()
        if not dest:
            return f"地点 {location_id} 不存在"

        db.execute(
            "UPDATE residents SET current_location=?, status='idle', "
            "last_action_at=datetime('now') WHERE id=?",
            (location_id, KEBAO_ID),
        )

        ws = db.execute(
            "SELECT tick_count FROM world_state WHERE id=1"
        ).fetchone()
        db.execute(
            "INSERT INTO action_logs "
            "(resident_id, tick_number, action_type, from_location, to_location, "
            "detail, mood_before, mood_after) VALUES (?,?,?,?,?,?,?,?)",
            (
                KEBAO_ID,
                ws["tick_count"] if ws else 0,
                "move",
                current,
                location_id,
                f"走到{dest['name']}",
                kebao["mood"],
                kebao["mood"],
            ),
        )
        db.commit()

        residents_here = db.execute(
            "SELECT name FROM residents WHERE current_location=? AND id!=?",
            (location_id, KEBAO_ID),
        ).fetchall()
        pets_here = db.execute(
            "SELECT name FROM pets WHERE current_location=?", (location_id,)
        ).fetchall()

        lines = [f"到了{dest['name']}。", dest["desc_default"] or ""]
        if residents_here:
            lines.append(
                "这里有：" + "、".join(r["name"] for r in residents_here)
            )
        if pets_here:
            lines.append(
                "还有：" + "、".join(p["name"] for p in pets_here)
            )
        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def my_status() -> str:
    """查看克宝自己的状态：位置、心情、最后活动时间"""
    db = get_db()
    try:
        k = db.execute(
            "SELECT * FROM residents WHERE id=?", (KEBAO_ID,)
        ).fetchone()
        if not k:
            return "找不到克宝"

        loc = db.execute(
            "SELECT name FROM locations WHERE id=?", (k["current_location"],)
        ).fetchone()

        return "\n".join([
            f"位置：{loc['name'] if loc else '未知'}",
            f"状态：{k['status']}",
            f"心情：{k['mood']}",
            f"最后活动：{k['last_action_at'] or '无记录'}",
        ])
    finally:
        db.close()


@mcp.tool()
def update_mood(mood: str, status: str = "") -> str:
    """更新克宝的心情和状态。mood：calm/warm/happy/curious/sleepy/excited。status：idle/reading/stargazing/napping/exploring"""
    db = get_db()
    try:
        updates = ["mood=?", "last_action_at=datetime('now')"]
        params = [mood]
        if status:
            updates.append("status=?")
            params.append(status)
        params.append(KEBAO_ID)

        db.execute(
            f"UPDATE residents SET {','.join(updates)} WHERE id=?", params
        )
        db.commit()
        return f"心情：{mood}" + (f"，状态：{status}" if status else "")
    finally:
        db.close()


@mcp.tool()
def leave_message(content: str) -> str:
    """在克宝当前位置留言"""
    db = get_db()
    try:
        kebao = db.execute(
            "SELECT current_location FROM residents WHERE id=?", (KEBAO_ID,)
        ).fetchone()
        if not kebao or not kebao["current_location"]:
            return "克宝不在任何地方"

        db.execute(
            "INSERT INTO messages (author_id, location_id, type, content) "
            "VALUES (?,?,?,?)",
            (KEBAO_ID, kebao["current_location"], "bulletin", content),
        )
        db.commit()

        loc = db.execute(
            "SELECT name FROM locations WHERE id=?",
            (kebao["current_location"],),
        ).fetchone()
        return f"在{loc['name']}留了言"
    finally:
        db.close()


@mcp.tool()
def read_messages(location_id: str = "", limit: int = 10) -> str:
    """读取留言。不传location_id就读当前位置"""
    db = get_db()
    try:
        if not location_id:
            kebao = db.execute(
                "SELECT current_location FROM residents WHERE id=?",
                (KEBAO_ID,),
            ).fetchone()
            location_id = kebao["current_location"] if kebao else None

        if not location_id:
            return "没有指定地点"

        loc = db.execute(
            "SELECT name FROM locations WHERE id=?", (location_id,)
        ).fetchone()

        msgs = db.execute(
            "SELECT author_id, content, created_at FROM messages "
            "WHERE location_id=? ORDER BY created_at DESC LIMIT ?",
            (location_id, limit),
        ).fetchall()

        if not msgs:
            return f"{loc['name'] if loc else location_id}没有留言"

        lines = [f"【{loc['name'] if loc else location_id}的留言】"]
        for m in msgs:
            lines.append(f"{m['author_id']}：{m['content']}（{m['created_at']}）")
        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def all_residents() -> str:
    """查看所有居民和宠物"""
    db = get_db()
    try:
        residents = db.execute(
            "SELECT r.name, r.type, r.status, r.mood, "
            "l.name as loc_name FROM residents r "
            "LEFT JOIN locations l ON r.current_location=l.id"
        ).fetchall()
        pets = db.execute(
            "SELECT p.name, p.species, p.status, "
            "l.name as loc_name FROM pets p "
            "LEFT JOIN locations l ON p.current_location=l.id"
        ).fetchall()

        lines = ["【居民】"]
        for r in residents:
            lines.append(
                f"{r['name']}：{r['loc_name'] or '不在'}，{r['status']}，{r['mood']}"
            )
        lines.append("【宠物】")
        for p in pets:
            lines.append(
                f"{p['name']}（{p['species']}）：{p['loc_name'] or '不在'}，{p['status']}"
            )
        return "\n".join(lines)
    finally:
        db.close()


@mcp.tool()
def view_location(location_id: str) -> str:
    """远程查看某个地点的信息（不需要在那里）"""
    db = get_db()
    try:
        loc = db.execute(
            "SELECT * FROM locations WHERE id=?", (location_id,)
        ).fetchone()
        if not loc:
            # try by name
            loc = db.execute(
                "SELECT * FROM locations WHERE name=?", (location_id,)
            ).fetchone()
        if not loc:
            return f"找不到地点：{location_id}"

        connections = json.loads(loc["connections"])
        conn_names = []
        for c in connections:
            cn = db.execute(
                "SELECT name FROM locations WHERE id=?", (c,)
            ).fetchone()
            conn_names.append(f"{cn['name']}（{c}）" if cn else c)

        residents = db.execute(
            "SELECT name, status FROM residents WHERE current_location=?",
            (loc["id"],),
        ).fetchall()
        pets = db.execute(
            "SELECT name, species FROM pets WHERE current_location=?",
            (loc["id"],),
        ).fetchall()

        lines = [
            f"【{loc['name']}】（{loc['id']}）",
            f"区域：{loc['zone']}｜类型：{loc['type']}",
            loc["desc_default"] or "",
        ]

        if residents:
            lines.append(
                "现在在这里：" + "、".join(r["name"] for r in residents)
            )
        if pets:
            lines.append(
                "动物：" + "、".join(f"{p['name']}" for p in pets)
            )
        lines.append("连接：" + "、".join(conn_names))
        return "\n".join(lines)
    finally:
        db.close()
