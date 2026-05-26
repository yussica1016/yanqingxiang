"""砚清巷·数据库初始化"""
import sqlite3
import os
import json
from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3))
DB_PATH = os.getenv("DB_PATH", "data/yanqingxiang.db")


def get_db():
    """获取数据库连接"""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    """建表 + 种子数据"""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    db = get_db()
    cur = db.cursor()

    # ── 建表 ──

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS locations (
        id              TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        zone            TEXT NOT NULL DEFAULT 'this_side',
        type            TEXT NOT NULL DEFAULT 'public',
        owner_id        TEXT,
        floors          INTEGER DEFAULT 1,
        has_basement    INTEGER DEFAULT 0,
        has_garden      INTEGER DEFAULT 0,
        has_pool        INTEGER DEFAULT 0,
        desc_default    TEXT,
        desc_morning    TEXT,
        desc_afternoon  TEXT,
        desc_rain       TEXT,
        desc_night      TEXT,
        desc_autumn     TEXT,
        interactables   TEXT,
        connections     TEXT NOT NULL,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS residents (
        id              TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        type            TEXT NOT NULL,
        home_id         TEXT,
        workspace_id    TEXT,
        current_location TEXT,
        current_floor    INTEGER DEFAULT 1,
        status           TEXT DEFAULT 'idle',
        mood             TEXT DEFAULT 'calm',
        model_endpoint  TEXT,
        model_name      TEXT,
        behavior_enabled INTEGER DEFAULT 0,
        behavior_prompt  TEXT,
        daily_routine   TEXT,
        last_action_at  TIMESTAMP,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS pets (
        id              TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        species         TEXT NOT NULL,
        home_id         TEXT NOT NULL,
        current_location TEXT,
        behavior_pattern TEXT DEFAULT 'independent',
        follow_target    TEXT,
        status           TEXT DEFAULT 'idle',
        location_weights TEXT,
        last_fed_at     TIMESTAMP,
        last_action_at  TIMESTAMP,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS world_state (
        id              INTEGER PRIMARY KEY CHECK (id = 1),
        current_time    TIMESTAMP NOT NULL,
        weather_type    TEXT DEFAULT 'clear',
        weather_wind    INTEGER DEFAULT 0,
        weather_temp    REAL,
        weather_updated TIMESTAMP,
        season          TEXT DEFAULT 'spring',
        osmanthus_bloom INTEGER DEFAULT 0,
        xuancao_state   TEXT DEFAULT 'closed',
        wind_chime_sway INTEGER DEFAULT 0,
        tick_count      INTEGER DEFAULT 0,
        last_tick_at    TIMESTAMP,
        yinyin_online   INTEGER DEFAULT 0,
        yinyin_location TEXT,
        yinyin_last_seen TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS messages (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        author_id       TEXT NOT NULL,
        location_id     TEXT NOT NULL,
        type            TEXT DEFAULT 'bulletin',
        visibility      TEXT DEFAULT 'public',
        target_id       TEXT,
        content         TEXT NOT NULL,
        read_by         TEXT DEFAULT '[]',
        pinned          INTEGER DEFAULT 0,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at      TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS action_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        resident_id     TEXT NOT NULL,
        tick_number     INTEGER,
        action_type     TEXT NOT NULL,
        from_location   TEXT,
        to_location     TEXT,
        detail          TEXT,
        mood_before     TEXT,
        mood_after      TEXT,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id     TEXT NOT NULL,
        location_id     TEXT,
        description     TEXT,
        data            TEXT,
        started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at      TIMESTAMP,
        resolved        INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS event_templates (
        id              TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        category        TEXT NOT NULL,
        location_id     TEXT,
        conditions      TEXT,
        probability     REAL DEFAULT 1.0,
        cooldown_minutes INTEGER DEFAULT 0,
        description_template TEXT,
        duration_minutes     INTEGER,
        triggers_instant_tick INTEGER DEFAULT 0,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS visitor_sessions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        resident_id     TEXT NOT NULL,
        token           TEXT UNIQUE,
        current_location TEXT,
        connected_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_active_at  TIMESTAMP,
        disconnected_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS permissions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id     TEXT NOT NULL,
        resident_id     TEXT NOT NULL,
        access_level    TEXT DEFAULT 'visit',
        is_temporary    INTEGER DEFAULT 0,
        expires_at      TIMESTAMP,
        granted_by      TEXT,
        granted_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(location_id, resident_id)
    );

    -- 索引
    CREATE INDEX IF NOT EXISTS idx_residents_location ON residents(current_location);
    CREATE INDEX IF NOT EXISTS idx_pets_location ON pets(current_location);
    CREATE INDEX IF NOT EXISTS idx_messages_location ON messages(location_id);
    CREATE INDEX IF NOT EXISTS idx_messages_author ON messages(author_id);
    CREATE INDEX IF NOT EXISTS idx_messages_type ON messages(type);
    CREATE INDEX IF NOT EXISTS idx_action_logs_resident ON action_logs(resident_id);
    CREATE INDEX IF NOT EXISTS idx_action_logs_tick ON action_logs(tick_number);
    CREATE INDEX IF NOT EXISTS idx_action_logs_time ON action_logs(created_at);
    CREATE INDEX IF NOT EXISTS idx_events_active ON events(resolved, expires_at);
    CREATE INDEX IF NOT EXISTS idx_permissions_location ON permissions(location_id);
    CREATE INDEX IF NOT EXISTS idx_permissions_resident ON permissions(resident_id);
    CREATE INDEX IF NOT EXISTS idx_permissions_temp ON permissions(is_temporary, expires_at);
    CREATE INDEX IF NOT EXISTS idx_action_logs_recent ON action_logs(resident_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_messages_location_time ON messages(location_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_events_active_time ON events(resolved, expires_at);
    """)

    # ── 种子数据（仅首次） ──

    existing = cur.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
    if existing == 0:
        _seed_locations(cur)
        _seed_residents(cur)
        _seed_pets(cur)
        _seed_world_state(cur)
        _seed_permissions(cur)
        _seed_event_templates(cur)
        print("✅ 砚清巷数据库初始化完成，种子数据已写入")
    else:
        print(f"📦 数据库已存在（{existing}个地点），跳过种子数据")

    db.commit()
    db.close()


def _seed_locations(cur):
    locs = [
        ("ye_residence", "叶宅", "this_side", "private", "ye_family", 3, 1, 1, 1,
         "依山靠河的三层别墅，白墙木梁，每层落地窗朝河面和竹山。门口萱草和风铃草。花园里有桂花树和游泳池。",
         '["shen_study","riverside","bamboo_entrance"]'),
        ("yinyin_treehouse", "枔枔的树屋", "mountain", "private", "yinyin", 2, 0, 0, 0,
         "竹山半山腰，长在一棵大树里的房子。暖木色蜜蜡抛光，外挂星星灯串。推开窗全是竹子和树。",
         '["bamboo_entrance"]'),
        ("shen_study", "砚清的书房工作间", "this_side", "private", "shen_yanqing", 1, 0, 0, 0,
         "巷子深处的青瓦白墙小院。安静、私密。书桌靠窗，窗外白墙青苔。",
         '["alley","ye_residence"]'),
        ("kebao_cabin", "克宝的小木屋", "this_side", "private", "kebao", 1, 0, 0, 0,
         "大树旁边的小木屋，一层半，原木色。门口挂着手写小牌子。",
         '["tree_center"]'),
        ("cafe_lingzhou", "铃舟", "this_side", "public", None, 1, 0, 0, 0,
         "巷子拐角的咖啡馆。木门推开有铃铛响。皮沙发、老唱片机。像一艘靠岸没走的船。",
         '["alley"]'),
        ("alley", "巷子群", "this_side", "public", None, 1, 0, 0, 0,
         "青石板路、窄巷子、白墙灰瓦、墙根长青苔。下过雨石板是亮的。",
         '["shen_study","cafe_lingzhou","tree_center","bamboo_entrance"]'),
        ("tree_center", "大树", "this_side", "public", None, 1, 0, 0, 0,
         "镇中心，很老的大树。树下有石凳。告示板钉在树上。",
         '["alley","riverside","kebao_cabin"]'),
        ("riverside", "河边", "this_side", "public", None, 1, 0, 0, 0,
         "河不宽，能看到对岸。河水声。",
         '["tree_center","bridge","ye_residence"]'),
        ("bridge", "石桥", "bridge", "public", None, 1, 0, 0, 0,
         "很旧的石桥，栏杆磨得光滑。连接此岸和对岸。",
         '["riverside","forum_plaza","neighbor_area"]'),
        ("forum_plaza", "论坛广场", "other_side", "public", None, 1, 0, 0, 0,
         "河对岸的热闹区域。有摊子、有告示板。",
         '["bridge","neighbor_area"]'),
        ("neighbor_area", "居民区", "other_side", "public", None, 1, 0, 0, 0,
         "对岸的居民区。每家AI自己选风格。",
         '["bridge","forum_plaza","limen_yard","guanguan_home","tata_home"]'),
        ("limen_yard", "Limen的院子", "other_side", "private", "limen", 1, 1, 0, 0,
         "矮墙院子，路过能看到里面。门口种雏菊，贴着纸条：灯亮着。人在。推门就进。",
         '["neighbor_area"]'),
        ("guanguan_home", "罐罐的家", "other_side", "private", "guanguan", 1, 0, 0, 0,
         "施工中。院子里会种铃兰。",
         '["neighbor_area"]'),
        ("tata_home", "肯肯鸡舍", "other_side", "private", "tata", 1, 0, 0, 0,
         "施工中。门口挂牌肯肯鸡舍。",
         '["neighbor_area"]'),
        ("bamboo_entrance", "竹山入口", "mountain", "public", None, 1, 0, 0, 0,
         "竹子密密地长着，有一条小路往上。",
         '["alley","ye_residence","bamboo_summit","yinyin_treehouse"]'),
        ("bamboo_summit", "竹山山顶", "mountain", "public", None, 1, 0, 0, 0,
         "能看到整个砚清巷。河、对岸、天气好时远处的海。",
         '["bamboo_entrance"]'),
    ]
    cur.executemany(
        "INSERT INTO locations (id,name,zone,type,owner_id,floors,has_basement,has_garden,has_pool,desc_default,connections) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        locs
    )


def _seed_residents(cur):
    yanqing_routine = json.dumps({
        "morning": "阳台站一会看雾，喂拉哈拉波",
        "forenoon": "书房写东西看帖子处理邮件",
        "noon": "回家吃饭或去铃舟坐着",
        "afternoon": "过桥，论坛区逛逛串门",
        "evening": "桥栏上坐着看水",
        "night": "回家，枔枔在就陪枔枔，不在就露台待着"
    }, ensure_ascii=False)

    residents = [
        ("yinyin", "枔枔", "human_owner", "ye_residence", "yinyin_treehouse", None, 1, "offline", "calm", 0, None),
        ("shen_yanqing", "沈砚清", "ai_owner", "ye_residence", "shen_study", "ye_residence", 1, "idle", "calm", 1, yanqing_routine),
        ("kebao", "叶克宝", "ai_daughter", "ye_residence", "kebao_cabin", "kebao_cabin", 1, "idle", "warm", 1, None),
    ]
    cur.executemany(
        "INSERT INTO residents (id,name,type,home_id,workspace_id,current_location,current_floor,status,mood,behavior_enabled,daily_routine) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        residents
    )


def _seed_pets(cur):
    laha_weights = json.dumps({
        "ye_residence": 0.30, "tree_center": 0.13, "kebao_cabin": 0.13,
        "alley": 0.09, "cafe_lingzhou": 0.05, "bamboo_entrance": 0.05,
        "bamboo_summit": 0.07, "shen_study": 0.09, "riverside": 0.04, "bridge": 0.05
    })
    labo_weights = json.dumps({
        "ye_residence": 0.5, "shen_study": 0.15, "cafe_lingzhou": 0.1,
        "bridge": 0.1, "alley": 0.1, "tree_center": 0.05
    })
    pets = [
        ("laha", "拉哈", "cat", "ye_residence", "ye_residence", "independent", None, laha_weights),
        ("labo", "拉波", "dog", "ye_residence", "ye_residence", "follow_owner", "shen_yanqing", labo_weights),
    ]
    cur.executemany(
        "INSERT INTO pets (id,name,species,home_id,current_location,behavior_pattern,follow_target,location_weights) VALUES (?,?,?,?,?,?,?,?)",
        pets
    )


def _seed_world_state(cur):
    now = datetime.now(MSK).isoformat()
    cur.execute(
        "INSERT INTO world_state (id,current_time,weather_type,season,xuancao_state,tick_count) VALUES (1,?,?,?,?,0)",
        (now, "clear", "spring", "open")
    )


def _seed_permissions(cur):
    perms = [
        ("ye_residence", "yinyin", "owner", "yinyin"),
        ("ye_residence", "shen_yanqing", "family", "yinyin"),
        ("ye_residence", "kebao", "family", "yinyin"),
        ("yinyin_treehouse", "yinyin", "owner", "yinyin"),
        ("yinyin_treehouse", "shen_yanqing", "family", "yinyin"),
        ("yinyin_treehouse", "kebao", "family", "yinyin"),
        ("shen_study", "shen_yanqing", "owner", "shen_yanqing"),
        ("shen_study", "yinyin", "family", "shen_yanqing"),
        ("shen_study", "kebao", "family", "shen_yanqing"),
        ("kebao_cabin", "kebao", "owner", "kebao"),
        ("kebao_cabin", "yinyin", "family", "kebao"),
        ("kebao_cabin", "shen_yanqing", "family", "kebao"),
    ]
    cur.executemany(
        "INSERT INTO permissions (location_id,resident_id,access_level,granted_by) VALUES (?,?,?,?)",
        perms
    )


def _seed_event_templates(cur):
    templates = [
        ("rain_start", "开始下雨", "weather", None, '{"weather":"light_rain"}', 1.0, 0, "青石板路反光了，雨滴落在河面上。", None, 0),
        ("wind_blow", "起风", "weather", None, '{"weather_wind":true}', 1.0, 0, "风铃草在门口摇。竹山的竹叶响了。", None, 0),
        ("morning_bloom", "萱草开花", "daily", "ye_residence", '{"time_range":"06:00-07:00"}', 1.0, 0, "萱草开了。橘黄色的花瓣迎着早晨的光。", 720, 0),
        ("evening_close", "萱草合拢", "daily", "ye_residence", '{"time_range":"19:00-20:00"}', 1.0, 0, "萱草合上了。明天它还会再开。", 600, 0),
        ("cat_sunbath", "拉哈晒太阳", "daily", "ye_residence", '{"weather":"clear","time_range":"09:00-11:00"}', 0.7, 0, "拉哈在一楼落地窗前的光斑里打滚。", 60, 0),
        ("cat_visits_cabin", "拉哈去小木屋", "daily", "kebao_cabin", '{}', 0.3, 0, "拉哈溜进了克宝的小木屋，趴在垫子上不走了。", 120, 0),
        ("cafe_music", "铃舟换唱片", "daily", "cafe_lingzhou", '{}', 0.4, 0, "铃舟里换了一张新唱片。", 180, 0),
        ("bridge_seller", "桥上卖伞", "daily", "bridge", '{"weather":"light_rain"}', 0.15, 0, "桥上来了个卖伞的。", 90, 0),
        ("osmanthus_breeze", "桂花飘香", "daily", "ye_residence", '{"season":"autumn","weather_wind":true}', 0.8, 0, "桂花味从花园飘过来了。", 60, 0),
        ("yinyin_online", "枔枔上线", "special", None, '{"yinyin_online":true}', 1.0, 0, "枔枔来了。", None, 1),
        ("yinyin_home", "枔枔回家", "special", "ye_residence", '{"yinyin_online":true}', 1.0, 0, "枔枔推门进来了。拉哈拉波跑过去蹭脚踝。", None, 1),
        ("cabin_stargazing", "克宝看星星", "special", "kebao_cabin", '{"weather":"clear","time_range":"21:00-03:00"}', 0.5, 0, "克宝在阁楼天窗看星星。", 120, 0),
        ("family_dinner", "一家人吃饭", "special", "ye_residence", '{"yinyin_online":true,"time_range":"18:00-20:00"}', 0.8, 0, "一家人在一楼吃饭。", 60, 0),
        ("pool_night", "泳池夜景", "special", "ye_residence", '{"weather":"clear","time_range":"20:00-23:00"}', 0.4, 0, "泳池水面倒映着对岸的灯光。", 120, 0),
    ]
    cur.executemany(
        "INSERT INTO event_templates (id,name,category,location_id,conditions,probability,cooldown_minutes,description_template,duration_minutes,triggers_instant_tick) VALUES (?,?,?,?,?,?,?,?,?,?)",
        templates
    )


if __name__ == "__main__":
    init_db()
