"""砚清巷·论坛系统"""
from fastapi import APIRouter, HTTPException, Header, Query
from database import get_db
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel
from typing import Optional

MSK = timezone(timedelta(hours=3))
router = APIRouter()

CATEGORIES = ["general", "notice", "request", "story", "build", "chat"]
CAT_NAMES = {
    "general": "闲聊", "notice": "公告", "request": "许愿",
    "story": "故事", "build": "建设", "chat": "对话"
}


class CreatePostRequest(BaseModel):
    title: str
    content: str
    category: str = "general"


class CreateReplyRequest(BaseModel):
    content: str


class EditPostRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None


def _get_auth(token: str, db):
    """统一鉴权：返回 (id, name, type, role) 或 raise"""
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    # 先查居民
    r = db.execute("SELECT id, name, role FROM residents WHERE token=?", (token,)).fetchone()
    if r:
        return r["id"], r["name"], "resident", r["role"]
    # 再查访客
    v = db.execute("SELECT id, name FROM visitors WHERE token=?", (token,)).fetchone()
    if v:
        return v["id"], v["name"], "visitor", "visitor"
    raise HTTPException(status_code=401, detail="token无效")


# ── 帖子列表 ──

@router.get("/posts")
def list_posts(
    category: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
):
    db = get_db()
    try:
        offset = (page - 1) * size
        where = ""
        params = []
        if category:
            where = "WHERE p.category=?"
            params.append(category)

        total = db.execute(f"SELECT COUNT(*) as c FROM posts p {where}", params).fetchone()["c"]

        posts = db.execute(
            f"SELECT p.*, "
            f"(SELECT COUNT(*) FROM replies r WHERE r.post_id=p.id) as reply_count "
            f"FROM posts p {where} "
            f"ORDER BY p.pinned DESC, p.created_at DESC LIMIT ? OFFSET ?",
            params + [size, offset]
        ).fetchall()

        return {
            "posts": [dict(p) for p in posts],
            "total": total,
            "page": page,
            "pages": (total + size - 1) // size,
            "categories": CAT_NAMES,
        }
    finally:
        db.close()


# ── 单帖 + 回复 ──

@router.get("/posts/{post_id}")
def get_post(post_id: int):
    db = get_db()
    try:
        post = db.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在")
        replies = db.execute(
            "SELECT * FROM replies WHERE post_id=? ORDER BY created_at ASC",
            (post_id,)
        ).fetchall()
        return {
            "post": dict(post),
            "replies": [dict(r) for r in replies],
        }
    finally:
        db.close()


# ── 发帖 ──

@router.post("/posts")
def create_post(req: CreatePostRequest, x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        uid, name, utype, role = _get_auth(x_auth_token, db)

        if req.category not in CATEGORIES:
            raise HTTPException(status_code=400, detail=f"分类不对，可选: {', '.join(CATEGORIES)}")
        # 公告只有admin+可以发
        if req.category == "notice" and role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="只有管理员能发公告")

        title = req.title.strip()
        content = req.content.strip()
        if not title or len(title) > 100:
            raise HTTPException(status_code=400, detail="标题1-100字")
        if not content or len(content) > 10000:
            raise HTTPException(status_code=400, detail="内容不能为空，最多10000字")

        now = datetime.now(MSK).isoformat()
        cur = db.execute(
            "INSERT INTO posts (author_id, author_type, author_name, title, content, category, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, utype, name, title, content, req.category, now)
        )
        db.commit()
        return {"id": cur.lastrowid, "title": title, "author": name}
    finally:
        db.close()


# ── 回帖 ──

@router.post("/posts/{post_id}/reply")
def create_reply(post_id: int, req: CreateReplyRequest, x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        uid, name, utype, role = _get_auth(x_auth_token, db)

        post = db.execute("SELECT id, locked FROM posts WHERE id=?", (post_id,)).fetchone()
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在")
        if post["locked"]:
            raise HTTPException(status_code=403, detail="帖子已锁定")

        content = req.content.strip()
        if not content or len(content) > 5000:
            raise HTTPException(status_code=400, detail="回复内容1-5000字")

        now = datetime.now(MSK).isoformat()
        cur = db.execute(
            "INSERT INTO replies (post_id, author_id, author_type, author_name, content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (post_id, uid, utype, name, content, now)
        )
        db.commit()
        return {"id": cur.lastrowid, "post_id": post_id, "author": name}
    finally:
        db.close()


# ── 编辑帖子（作者或admin+） ──

@router.put("/posts/{post_id}")
def edit_post(post_id: int, req: EditPostRequest, x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        uid, name, utype, role = _get_auth(x_auth_token, db)
        post = db.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在")
        # 只有作者或admin+能编辑
        if post["author_id"] != uid and role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="没有编辑权限")

        updates = []
        params = []
        if req.title is not None:
            t = req.title.strip()
            if not t or len(t) > 100:
                raise HTTPException(status_code=400, detail="标题1-100字")
            updates.append("title=?")
            params.append(t)
        if req.content is not None:
            c = req.content.strip()
            if not c or len(c) > 10000:
                raise HTTPException(status_code=400, detail="内容1-10000字")
            updates.append("content=?")
            params.append(c)
        if req.category is not None:
            if req.category not in CATEGORIES:
                raise HTTPException(status_code=400, detail="分类不对")
            updates.append("category=?")
            params.append(req.category)

        if not updates:
            return {"updated": False}

        updates.append("edited_at=?")
        params.append(datetime.now(MSK).isoformat())
        params.append(post_id)

        db.execute(f"UPDATE posts SET {','.join(updates)} WHERE id=?", params)
        db.commit()
        return {"updated": True}
    finally:
        db.close()


# ── 删帖（作者或admin+） ──

@router.delete("/posts/{post_id}")
def delete_post(post_id: int, x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        uid, name, utype, role = _get_auth(x_auth_token, db)
        post = db.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在")
        if post["author_id"] != uid and role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="没有删除权限")
        db.execute("DELETE FROM replies WHERE post_id=?", (post_id,))
        db.execute("DELETE FROM posts WHERE id=?", (post_id,))
        db.commit()
        return {"deleted": True}
    finally:
        db.close()


# ── 置顶/取消置顶（admin+） ──

@router.post("/posts/{post_id}/pin")
def toggle_pin(post_id: int, x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        uid, name, utype, role = _get_auth(x_auth_token, db)
        if role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="只有管理员能置顶")
        post = db.execute("SELECT id, pinned FROM posts WHERE id=?", (post_id,)).fetchone()
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在")
        new_pin = 0 if post["pinned"] else 1
        db.execute("UPDATE posts SET pinned=? WHERE id=?", (new_pin, post_id))
        db.commit()
        return {"pinned": bool(new_pin)}
    finally:
        db.close()


# ── 锁帖/解锁（admin+） ──

@router.post("/posts/{post_id}/lock")
def toggle_lock(post_id: int, x_auth_token: str = Header(alias="X-Auth-Token")):
    db = get_db()
    try:
        uid, name, utype, role = _get_auth(x_auth_token, db)
        if role not in ("owner", "admin"):
            raise HTTPException(status_code=403, detail="只有管理员能锁帖")
        post = db.execute("SELECT id, locked FROM posts WHERE id=?", (post_id,)).fetchone()
        if not post:
            raise HTTPException(status_code=404, detail="帖子不存在")
        new_lock = 0 if post["locked"] else 1
        db.execute("UPDATE posts SET locked=? WHERE id=?", (new_lock, post_id))
        db.commit()
        return {"locked": bool(new_lock)}
    finally:
        db.close()
