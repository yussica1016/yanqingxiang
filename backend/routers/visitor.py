"""砚清巷·认证 + 访客 + 居民自编辑"""
from fastapi import APIRouter, HTTPException, Header
from database import get_db
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel
from typing import Optional
import uuid
import json
import secrets

MSK = timezone(timedelta(hours=3))
router = APIRouter()

AVATARS = ["🧑","👤","🐱","🐶","🌸","🍃","🌙","⭐","🎵","🦊","🐰","🐻","🌻","🍀","🎐"]


# ── 请求模型 ──

class RegisterRequest(BaseModel):
    invite_code: str
    name: str
    avatar_emoji: str = "🧑"

class ResidentLoginRequest(BaseModel):
    username: str
    password: str

class MoveRequest(BaseModel):
    location_id: str

class EditProfileRequest(BaseModel):
    bio: Optional[str] = None
    avatar_emoji: Optional[str] = None
    password: Optional[str] = None

class EditLocationRequest(BaseModel):
    name: Optional[str] = None
    desc_default: Optional[str] = None
    desc_morning: Optional[str] = None
    desc_night: Optional[str] = None
    desc_rain: Optional[str] = None
    desc_autumn: Optional[str] = None
    floors: Optional[int] = None
    has_basement: Optional[bool] = None
    has_garden: Optional[bool] = None
    has_pool: Optional[bool] = None
    interactables: Optional[str] = None


class CreateLandRequest(BaseModel):
    """管理员给居民分配地皮"""
    land_id: str          # 地点id，英文下划线
    land_name: str        # 显示名
    owner_id: str         # 分配给谁
    zone: str = "other_side"
    connect_to: str = "neighbor_area"  # 连通到哪个已有地点


# ── 统一鉴权 ──

def get_auth(token: str, db):
    """返回 dict: id, name, type, role"""
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    r = db.execute("SELECT id, name, type, role, avatar_emoji FROM residents WHERE token=?", (token,)).fetchone()
    if r:
        return {"id": r["id"], "name": r["name"], "type": "resident", "role": r["role"], "avatar": r["avatar_emoji"]}
    v = db.execute("SELECT id, name, avatar_emoji FROM visitors WHERE token=?", (token,)).fetchone()
    if v:
        return {"id": v["id"], "name": v["name"], "type": "visitor", "role": "visitor", "avatar": v["avatar_emoji"]}
    raise HTTPException(status_code=401, detail="token无效")


# ═══ 居民登录（统一入口，owner/admin/resident都走这里） ═══

@router.post("/resident/login")
def resident_login(req: ResidentLoginRequest):
    db = get_db()
    try:
        # 按名字或id查
        r = db.execute(
            "SELECT * FROM residents WHERE (id=? OR name=?) AND password=?",
            (req.username, req.username, req.password)
        ).fetchone()
        if not r:
            raise HTTPException(status_code=401, detail="用户名或密码不对")

        token = secrets.token_urlsafe(32)
        now = datetime.now(MSK).isoformat()

        db.execute("UPDATE residents SET token=?, last_action_at=? WHERE id=?", (token, now, r["id"]))

        # 枔枔上线同步world_state
        if r["id"] == "yinyin":
            loc = r["current_location"] or "ye_residence"
            db.execute(
                "UPDATE world_state SET yinyin_online=1, yinyin_location=?, yinyin_last_seen=? WHERE id=1",
                (loc, now)
            )

        db.commit()

        return {
            "id": r["id"],
            "name": r["name"],
            "role": r["role"],
            "token": token,
            "location": r["current_location"] or r["home_id"] or "ye_residence",
            "avatar": r["avatar_emoji"],
            "bio": r["bio"],
        }
    finally:
        db.close()


# ═══ 访客注册 ═══

@router.post("/register")
def register_visitor(req: RegisterRequest):
    db = get_db()
    try:
        code = db.execute("SELECT * FROM invite_codes WHERE code=?", (req.invite_code,)).fetchone()
        if not code:
            raise HTTPException(status_code=400, detail="邀请码不存在")
        if code["max_uses"] > 0 and code["used_count"] >= code["max_uses"]:
            raise HTTPException(status_code=400, detail="邀请码已用完")
        if code["expires_at"]:
            if code["expires_at"] < datetime.now(MSK).isoformat():
                raise HTTPException(status_code=400, detail="邀请码已过期")

        name = req.name.strip()
        if not name or len(name) > 20:
            raise HTTPException(status_code=400, detail="名字1-20个字")
        if db.execute("SELECT id FROM visitors WHERE name=?", (name,)).fetchone():
            raise HTTPException(status_code=400, detail="名字已被占用")
        if db.execute("SELECT id FROM residents WHERE name=?", (name,)).fetchone():
            raise HTTPException(status_code=400, detail="名字已被占用")

        vid = f"visitor_{uuid.uuid4().hex[:8]}"
        token = secrets.token_urlsafe(32)
        now = datetime.now(MSK).isoformat()

        db.execute(
            "INSERT INTO visitors (id, name, invite_code, token, current_location, avatar_emoji, last_active_at) "
            "VALUES (?, ?, ?, ?, 'forum_plaza', ?, ?)",
            (vid, name, req.invite_code, token, req.avatar_emoji, now)
        )
        db.execute("UPDATE invite_codes SET used_count=used_count+1 WHERE code=?", (req.invite_code,))
        db.commit()

        return {
            "id": vid, "name": name, "token": token,
            "role": "visitor", "location": "forum_plaza",
            "avatar": req.avatar_emoji,
        }
    finally:
        db.close()


# ═══ Token恢复会话 ═══

@router.post("/restore")
def restore_session(x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        auth = get_auth(x_auth_token, db)
        now = datetime.now(MSK).isoformat()

        if auth["type"] == "resident":
            r = db.execute("SELECT current_location, home_id, role, bio FROM residents WHERE id=?", (auth["id"],)).fetchone()
            loc = r["current_location"] or r["home_id"]
            if auth["id"] == "yinyin":
                db.execute("UPDATE world_state SET yinyin_online=1, yinyin_last_seen=? WHERE id=1", (now,))
                db.commit()
            return {**auth, "location": loc, "bio": r["bio"]}
        else:
            v = db.execute("SELECT current_location FROM visitors WHERE id=?", (auth["id"],)).fetchone()
            db.execute("UPDATE visitors SET is_online=1, last_active_at=? WHERE id=?", (now, auth["id"]))
            db.commit()
            return {**auth, "location": v["current_location"]}
    finally:
        db.close()


# ═══ 移动 ═══

@router.post("/move")
def do_move(req: MoveRequest, x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        auth = get_auth(x_auth_token, db)
        loc = db.execute("SELECT * FROM locations WHERE id=?", (req.location_id,)).fetchone()
        if not loc:
            raise HTTPException(status_code=404, detail="地点不存在")

        # 获取当前位置
        if auth["type"] == "resident":
            r = db.execute("SELECT current_location, home_id, role FROM residents WHERE id=?", (auth["id"],)).fetchone()
            current = r["current_location"] or r["home_id"]
            is_owner_or_admin = r["role"] in ("owner", "admin")
        else:
            v = db.execute("SELECT current_location FROM visitors WHERE id=?", (auth["id"],)).fetchone()
            current = v["current_location"]
            is_owner_or_admin = False

        # 检查连通
        cur_loc = db.execute("SELECT connections FROM locations WHERE id=?", (current,)).fetchone()
        if cur_loc:
            conns = json.loads(cur_loc["connections"])
            if req.location_id not in conns and req.location_id != current:
                raise HTTPException(status_code=400, detail="走不过去，路不通")

        # 私有地点权限
        if loc["type"] == "private" and not is_owner_or_admin:
            # 居民可以进自己的家
            is_home = (auth["type"] == "resident" and loc["owner_id"] == auth["id"])
            has_perm = db.execute(
                "SELECT id FROM permissions WHERE location_id=? AND resident_id=?",
                (req.location_id, auth["id"])
            ).fetchone()
            if not is_home and not has_perm:
                raise HTTPException(status_code=403, detail="私人地方，没有权限进入")

        now = datetime.now(MSK).isoformat()

        # 更新位置
        if auth["type"] == "resident":
            db.execute("UPDATE residents SET current_location=?, last_action_at=? WHERE id=?",
                       (req.location_id, now, auth["id"]))
            if auth["id"] == "yinyin":
                db.execute("UPDATE world_state SET yinyin_location=?, yinyin_last_seen=? WHERE id=1",
                           (req.location_id, now))
        else:
            db.execute("UPDATE visitors SET current_location=?, last_active_at=? WHERE id=?",
                       (req.location_id, now, auth["id"]))

        db.commit()
        return {"moved": True, "from": current, "to": req.location_id,
                "location_name": loc["name"], "description": loc["desc_default"]}
    finally:
        db.close()


# ═══ 下线 ═══

@router.post("/logout")
def do_logout(x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        auth = get_auth(x_auth_token, db)
        now = datetime.now(MSK).isoformat()
        if auth["type"] == "resident":
            if auth["id"] == "yinyin":
                db.execute("UPDATE world_state SET yinyin_online=0, yinyin_last_seen=? WHERE id=1", (now,))
            db.execute("UPDATE residents SET token=NULL, last_action_at=? WHERE id=?", (now, auth["id"]))
        else:
            db.execute("UPDATE visitors SET is_online=0, last_active_at=? WHERE id=?", (now, auth["id"]))
        db.commit()
        return {"status": "offline"}
    finally:
        db.close()


# ═══ 编辑个人资料（居民） ═══

@router.put("/profile")
def edit_profile(req: EditProfileRequest, x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        auth = get_auth(x_auth_token, db)
        if auth["type"] != "resident":
            raise HTTPException(status_code=403, detail="只有居民能编辑资料")

        updates, params = [], []
        if req.bio is not None:
            if len(req.bio) > 200:
                raise HTTPException(status_code=400, detail="简介最多200字")
            updates.append("bio=?"); params.append(req.bio)
        if req.avatar_emoji is not None:
            updates.append("avatar_emoji=?"); params.append(req.avatar_emoji)
        if req.password is not None:
            if len(req.password) < 4:
                raise HTTPException(status_code=400, detail="密码至少4位")
            updates.append("password=?"); params.append(req.password)
        if not updates:
            return {"updated": False}
        params.append(auth["id"])
        db.execute(f"UPDATE residents SET {','.join(updates)} WHERE id=?", params)
        db.commit()
        return {"updated": True}
    finally:
        db.close()


# ═══ 编辑自己的房子（居民编辑自己拥有的地点） ═══

@router.put("/location/{location_id}")
def edit_own_location(location_id: str, req: EditLocationRequest, x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        auth = get_auth(x_auth_token, db)
        if auth["type"] != "resident":
            raise HTTPException(status_code=403, detail="只有居民能编辑地点")

        loc = db.execute("SELECT * FROM locations WHERE id=?", (location_id,)).fetchone()
        if not loc:
            raise HTTPException(status_code=404, detail="地点不存在")

        # 必须是自己拥有的，或者是owner/admin
        role = db.execute("SELECT role FROM residents WHERE id=?", (auth["id"],)).fetchone()["role"]
        is_own = (loc["owner_id"] == auth["id"])
        if not is_own and role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="只能编辑自己的地方")

        updates, params = [], []
        if req.desc_default is not None:
            if len(req.desc_default) > 500:
                raise HTTPException(status_code=400, detail="描述最多500字")
            updates.append("desc_default=?"); params.append(req.desc_default)
        if req.name is not None:
            if not req.name.strip() or len(req.name) > 30:
                raise HTTPException(status_code=400, detail="地点名1-30字")
            updates.append("name=?"); params.append(req.name.strip())
        for field in ("desc_morning", "desc_night", "desc_rain", "desc_autumn"):
            val = getattr(req, field, None)
            if val is not None:
                if len(val) > 500:
                    raise HTTPException(status_code=400, detail=f"{field}最多500字")
                updates.append(f"{field}=?"); params.append(val)
        if req.floors is not None:
            if req.floors < 1 or req.floors > 5:
                raise HTTPException(status_code=400, detail="楼层1-5")
            updates.append("floors=?"); params.append(req.floors)
        if req.has_basement is not None:
            updates.append("has_basement=?"); params.append(1 if req.has_basement else 0)
        if req.has_garden is not None:
            updates.append("has_garden=?"); params.append(1 if req.has_garden else 0)
        if req.has_pool is not None:
            updates.append("has_pool=?"); params.append(1 if req.has_pool else 0)
        if req.interactables is not None:
            if len(req.interactables) > 1000:
                raise HTTPException(status_code=400, detail="interactables最多1000字")
            updates.append("interactables=?"); params.append(req.interactables)
        if not updates:
            return {"updated": False}
        params.append(location_id)
        db.execute(f"UPDATE locations SET {','.join(updates)} WHERE id=?", params)
        db.commit()
        return {"updated": True}
    finally:
        db.close()


# ═══ 分配地皮（admin+创建新地点给居民） ═══

@router.post("/land/create")
def create_land(req: CreateLandRequest, x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        auth = get_auth(x_auth_token, db)
        if auth["role"] not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="只有管理员能分配地皮")

        # 检查id合法
        if not req.land_id or not req.land_id.replace("_", "").isalnum():
            raise HTTPException(status_code=400, detail="地点id只能用英文字母数字下划线")
        if len(req.land_id) > 30:
            raise HTTPException(status_code=400, detail="地点id最多30字符")
        if db.execute("SELECT id FROM locations WHERE id=?", (req.land_id,)).fetchone():
            raise HTTPException(status_code=400, detail="这个id已经有地方了")

        # 检查分配对象存在
        target = db.execute("SELECT id, name FROM residents WHERE id=?", (req.owner_id,)).fetchone()
        if not target:
            raise HTTPException(status_code=404, detail="找不到这个居民")

        # 检查连通的地点存在
        connect = db.execute("SELECT id, connections FROM locations WHERE id=?", (req.connect_to,)).fetchone()
        if not connect:
            raise HTTPException(status_code=404, detail="连通地点不存在")

        name = req.land_name.strip()
        if not name or len(name) > 30:
            raise HTTPException(status_code=400, detail="地点名1-30字")

        # 创建地点
        connections = json.dumps([req.connect_to])
        db.execute(
            "INSERT INTO locations (id, name, zone, type, owner_id, floors, desc_default, connections) "
            "VALUES (?, ?, ?, 'private', ?, 1, '刚划好的地，等主人来装修。', ?)",
            (req.land_id, name, req.zone, req.owner_id, connections)
        )

        # 更新连通地点的connections，加上新地点
        old_conns = json.loads(connect["connections"])
        old_conns.append(req.land_id)
        db.execute("UPDATE locations SET connections=? WHERE id=?", (json.dumps(old_conns), req.connect_to))

        # 添加owner权限
        db.execute(
            "INSERT INTO permissions (location_id, resident_id, access_level, granted_by) VALUES (?, ?, 'owner', ?)",
            (req.land_id, req.owner_id, auth["id"])
        )

        # 更新居民home_id
        db.execute("UPDATE residents SET home_id=? WHERE id=? AND home_id IS NULL", (req.land_id, req.owner_id))

        db.commit()
        return {
            "created": True,
            "land_id": req.land_id,
            "name": name,
            "owner": target["name"],
            "connected_to": req.connect_to,
        }
    finally:
        db.close()


# ═══ 在线列表 ═══

@router.get("/online")
def get_online():
    db = get_db()
    try:
        residents_online = db.execute(
            "SELECT id, name, role, avatar_emoji, current_location FROM residents WHERE token IS NOT NULL"
        ).fetchall()
        visitors_online = db.execute(
            "SELECT id, name, avatar_emoji, current_location FROM visitors WHERE is_online=1"
        ).fetchall()
        return {
            "residents": [dict(r) for r in residents_online],
            "visitors": [dict(v) for v in visitors_online],
        }
    finally:
        db.close()


# ═══ 邀请码 ═══

@router.post("/invite/create")
def create_invite(max_uses: int = 1, x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        auth = get_auth(x_auth_token, db)
        if auth["role"] not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="只有管理员能生成邀请码")
        code = secrets.token_urlsafe(6)
        db.execute(
            "INSERT INTO invite_codes (code, created_by, max_uses, created_at) VALUES (?, ?, ?, ?)",
            (code, auth["id"], max_uses, datetime.now(MSK).isoformat())
        )
        db.commit()
        return {"code": code, "max_uses": max_uses}
    finally:
        db.close()


@router.get("/invite/list")
def list_invites(x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        auth = get_auth(x_auth_token, db)
        if auth["role"] not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="只有管理员能查看邀请码")
        codes = db.execute("SELECT * FROM invite_codes ORDER BY created_at DESC").fetchall()
        return {"codes": [dict(c) for c in codes]}
    finally:
        db.close()


# ═══ 居民列表（公开） ═══

@router.get("/residents")
def list_residents():
    db = get_db()
    try:
        rs = db.execute(
            "SELECT id, name, type, role, bio, avatar_emoji, home_id, current_location, status, mood "
            "FROM residents ORDER BY role DESC"
        ).fetchall()
        return {"residents": [dict(r) for r in rs]}
    finally:
        db.close()
