"""砚清巷·访客系统"""
from fastapi import APIRouter, HTTPException, Header
from database import get_db
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel
import uuid
import json
import secrets

MSK = timezone(timedelta(hours=3))
router = APIRouter()

# ── 管理员密码（枔枔用） ──
OWNER_PASSWORD = "yanqingxiang2026"

AVATAR_OPTIONS = ["🧑", "👤", "🐱", "🐶", "🌸", "🍃", "🌙", "⭐", "🎵", "🦊", "🐰", "🐻", "🌻", "🍀", "🎐"]


class RegisterRequest(BaseModel):
    invite_code: str
    name: str
    avatar_emoji: str = "🧑"


class OwnerLoginRequest(BaseModel):
    password: str


class MoveRequest(BaseModel):
    location_id: str


# ── 访客注册 ──

@router.post("/register")
def register_visitor(req: RegisterRequest):
    """用邀请码注册，自己起名字"""
    db = get_db()
    try:
        # 检查邀请码
        code = db.execute(
            "SELECT * FROM invite_codes WHERE code=?", (req.invite_code,)
        ).fetchone()
        if not code:
            raise HTTPException(status_code=400, detail="邀请码不存在")
        if code["max_uses"] > 0 and code["used_count"] >= code["max_uses"]:
            raise HTTPException(status_code=400, detail="邀请码已用完")
        if code["expires_at"]:
            now = datetime.now(MSK).isoformat()
            if code["expires_at"] < now:
                raise HTTPException(status_code=400, detail="邀请码已过期")

        # 检查名字
        name = req.name.strip()
        if not name or len(name) > 20:
            raise HTTPException(status_code=400, detail="名字1-20个字")
        existing = db.execute("SELECT id FROM visitors WHERE name=?", (name,)).fetchone()
        if existing:
            raise HTTPException(status_code=400, detail="这个名字已经有人用了")
        # 也不能和居民重名
        res_exist = db.execute("SELECT id FROM residents WHERE name=?", (name,)).fetchone()
        if res_exist:
            raise HTTPException(status_code=400, detail="这个名字已经有人用了")

        # 创建访客
        visitor_id = f"visitor_{uuid.uuid4().hex[:8]}"
        token = secrets.token_urlsafe(32)
        now = datetime.now(MSK).isoformat()

        db.execute(
            "INSERT INTO visitors (id, name, invite_code, token, current_location, avatar_emoji, last_active_at) "
            "VALUES (?, ?, ?, ?, 'forum_plaza', ?, ?)",
            (visitor_id, name, req.invite_code, token, req.avatar_emoji, now)
        )

        # 更新邀请码使用次数
        db.execute(
            "UPDATE invite_codes SET used_count = used_count + 1 WHERE code=?",
            (req.invite_code,)
        )

        db.commit()
        return {
            "visitor_id": visitor_id,
            "name": name,
            "token": token,
            "location": "forum_plaza",
            "message": f"欢迎来到砚清巷，{name}。你在论坛广场。"
        }
    finally:
        db.close()


@router.post("/login")
def visitor_login(token: str = Header(alias="X-Visitor-Token")):
    """用token恢复会话"""
    db = get_db()
    try:
        v = db.execute("SELECT * FROM visitors WHERE token=?", (token,)).fetchone()
        if not v:
            raise HTTPException(status_code=401, detail="token无效")
        now = datetime.now(MSK).isoformat()
        db.execute(
            "UPDATE visitors SET is_online=1, last_active_at=? WHERE id=?",
            (now, v["id"])
        )
        db.commit()
        return {
            "visitor_id": v["id"],
            "name": v["name"],
            "location": v["current_location"],
            "avatar_emoji": v["avatar_emoji"],
        }
    finally:
        db.close()


# ── 主人登录 ──

@router.post("/owner/login")
def owner_login(req: OwnerLoginRequest):
    """枔枔用密码登录"""
    if req.password != OWNER_PASSWORD:
        raise HTTPException(status_code=401, detail="密码不对")
    db = get_db()
    try:
        now = datetime.now(MSK).isoformat()
        db.execute(
            "UPDATE world_state SET yinyin_online=1, yinyin_last_seen=? WHERE id=1",
            (now,)
        )
        # 如果没有位置，默认叶宅
        ws = db.execute("SELECT yinyin_location FROM world_state WHERE id=1").fetchone()
        if not ws["yinyin_location"]:
            db.execute("UPDATE world_state SET yinyin_location='ye_residence' WHERE id=1", )
        db.commit()
        loc = ws["yinyin_location"] or "ye_residence"
        return {
            "role": "owner",
            "name": "叶枔枖",
            "location": loc,
            "message": "叶枔枖来了。"
        }
    finally:
        db.close()


# ── 移动 ──

@router.post("/move")
def visitor_move(req: MoveRequest, token: str = Header(alias="X-Visitor-Token")):
    """访客移动到指定地点"""
    db = get_db()
    try:
        v = db.execute("SELECT * FROM visitors WHERE token=?", (token,)).fetchone()
        if not v:
            raise HTTPException(status_code=401, detail="token无效")

        # 检查目标地点是否存在
        loc = db.execute("SELECT * FROM locations WHERE id=?", (req.location_id,)).fetchone()
        if not loc:
            raise HTTPException(status_code=404, detail="地点不存在")

        # 检查连通性——访客当前位置到目标是否相连
        current_loc = db.execute(
            "SELECT connections FROM locations WHERE id=?", (v["current_location"],)
        ).fetchone()
        if current_loc:
            connections = json.loads(current_loc["connections"])
            if req.location_id not in connections and req.location_id != v["current_location"]:
                raise HTTPException(status_code=400, detail="走不过去，路不通")

        # 私有地点检查
        if loc["type"] == "private":
            perm = db.execute(
                "SELECT * FROM permissions WHERE location_id=? AND resident_id=?",
                (req.location_id, v["id"])
            ).fetchone()
            if not perm:
                raise HTTPException(status_code=403, detail="这是私人地方，你还没有权限进入")

        now = datetime.now(MSK).isoformat()
        old_location = v["current_location"]
        db.execute(
            "UPDATE visitors SET current_location=?, last_active_at=? WHERE id=?",
            (req.location_id, now, v["id"])
        )
        db.commit()
        return {
            "moved": True,
            "from": old_location,
            "to": req.location_id,
            "location_name": loc["name"],
            "description": loc["desc_default"],
        }
    finally:
        db.close()


@router.post("/owner/move")
def owner_move(req: MoveRequest):
    """枔枔移动"""
    db = get_db()
    try:
        ws = db.execute("SELECT yinyin_online, yinyin_location FROM world_state WHERE id=1").fetchone()
        if not ws or not ws["yinyin_online"]:
            raise HTTPException(status_code=400, detail="你还没上线")

        loc = db.execute("SELECT * FROM locations WHERE id=?", (req.location_id,)).fetchone()
        if not loc:
            raise HTTPException(status_code=404, detail="地点不存在")

        # 枔枔也要走连通路径（但枔枔是主人，private不限制）
        current = ws["yinyin_location"] or "ye_residence"
        current_loc = db.execute("SELECT connections FROM locations WHERE id=?", (current,)).fetchone()
        if current_loc:
            connections = json.loads(current_loc["connections"])
            if req.location_id not in connections and req.location_id != current:
                raise HTTPException(status_code=400, detail="走不过去，路不通")

        now = datetime.now(MSK).isoformat()
        db.execute(
            "UPDATE world_state SET yinyin_location=?, yinyin_last_seen=? WHERE id=1",
            (req.location_id, now)
        )
        db.commit()
        return {
            "moved": True,
            "from": current,
            "to": req.location_id,
            "location_name": loc["name"],
            "description": loc["desc_default"],
        }
    finally:
        db.close()


# ── 枔枔下线 ──

@router.post("/owner/offline")
def owner_offline():
    """枔枔下线"""
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


# ── 访客下线 ──

@router.post("/offline")
def visitor_offline(token: str = Header(alias="X-Visitor-Token")):
    db = get_db()
    try:
        v = db.execute("SELECT id FROM visitors WHERE token=?", (token,)).fetchone()
        if not v:
            raise HTTPException(status_code=401, detail="token无效")
        now = datetime.now(MSK).isoformat()
        db.execute("UPDATE visitors SET is_online=0, last_active_at=? WHERE id=?", (now, v["id"]))
        db.commit()
        return {"status": "offline"}
    finally:
        db.close()


# ── 在线访客列表 ──

@router.get("/online")
def get_online_visitors():
    db = get_db()
    try:
        visitors = db.execute(
            "SELECT id, name, current_location, avatar_emoji, last_active_at "
            "FROM visitors WHERE is_online=1 ORDER BY last_active_at DESC"
        ).fetchall()
        return {"visitors": [dict(v) for v in visitors]}
    finally:
        db.close()


# ── 邀请码管理 ──

@router.post("/invite/create")
def create_invite_code(max_uses: int = 1):
    """生成邀请码（管理用）"""
    db = get_db()
    try:
        code = secrets.token_urlsafe(6)  # ~8字符
        now = datetime.now(MSK).isoformat()
        db.execute(
            "INSERT INTO invite_codes (code, created_by, max_uses, created_at) VALUES (?, 'yinyin', ?, ?)",
            (code, max_uses, now)
        )
        db.commit()
        return {"code": code, "max_uses": max_uses}
    finally:
        db.close()


@router.get("/invite/list")
def list_invite_codes():
    """列出所有邀请码"""
    db = get_db()
    try:
        codes = db.execute("SELECT * FROM invite_codes ORDER BY created_at DESC").fetchall()
        return {"codes": [dict(c) for c in codes]}
    finally:
        db.close()
