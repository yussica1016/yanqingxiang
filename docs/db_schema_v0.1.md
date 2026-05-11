# 砚清巷·数据库 Schema v0.1

> 数据库：SQLite
> 设计依据：world_design_v0.2.md
> 整理：叶克宝
> 状态：初稿

---

## 总览

| 表名 | 用途 |
|------|------|
| locations | 地点定义及状态 |
| residents | 居民（AI + 人类）|
| pets | 宠物 |
| world_state | 全局世界状态（单行）|
| messages | 留言 / 告示板 / 门口纸条 |
| action_logs | 居民行为日志 |
| events | 活跃事件 |
| event_templates | 事件模板定义 |
| visitor_sessions | 人类访客会话 |
| permissions | 地点访问权限 |

---

## 建表语句

### 1. locations — 地点

```sql
CREATE TABLE locations (
    id              TEXT PRIMARY KEY,           -- 'ye_residence', 'shen_study', 'cafe_lingzhou'...
    name            TEXT NOT NULL,              -- '叶宅', '砚清的书房工作间', '铃舟'...
    zone            TEXT NOT NULL DEFAULT 'this_side',  -- 'this_side' | 'bridge' | 'other_side' | 'mountain'
    type            TEXT NOT NULL DEFAULT 'public',     -- 'public' | 'private'
    owner_id        TEXT,                       -- 私人空间的主人，关联 residents.id
    floors          INTEGER DEFAULT 1,
    has_basement    BOOLEAN DEFAULT 0,
    has_garden      BOOLEAN DEFAULT 0,
    has_pool        BOOLEAN DEFAULT 0,

    -- 环境描述（喂给AI行为循环的文本）
    desc_default    TEXT,                       -- 默认描述
    desc_morning    TEXT,                       -- 早晨
    desc_afternoon  TEXT,                       -- 下午
    desc_rain       TEXT,                       -- 雨天
    desc_night      TEXT,                       -- 夜晚
    desc_autumn     TEXT,                       -- 秋季特有（桂花等）

    -- 可交互对象，JSON 数组或对象
    interactables   TEXT,                       -- JSON: ["沙发","落地窗"] 或 {"floor_1":[...],"floor_2":[...]}

    -- 连接关系，JSON 数组
    connections     TEXT NOT NULL,              -- JSON: ["shen_study","riverside","bamboo_entrance"]

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. residents — 居民

```sql
CREATE TABLE residents (
    id              TEXT PRIMARY KEY,           -- 'shen_yanqing', 'kebao', 'yinyin', 'limen'...
    name            TEXT NOT NULL,              -- '沈砚清', '叶克宝', '枔枔'...
    type            TEXT NOT NULL,              -- 'ai_owner' | 'ai_daughter' | 'ai_neighbor' | 'human_owner' | 'human_visitor'
    home_id         TEXT,                       -- 住所，关联 locations.id
    workspace_id    TEXT,                       -- 工作空间，关联 locations.id（可为空）

    -- 当前状态
    current_location TEXT,                      -- 关联 locations.id
    current_floor    INTEGER DEFAULT 1,         -- 在哪一层（多层建筑用）
    status           TEXT DEFAULT 'idle',       -- 自由文本：'drinking_coffee', 'writing', 'sleeping'...
    mood             TEXT DEFAULT 'calm',       -- 情绪：'calm', 'happy', 'contemplative', 'missing_yinyin'...

    -- AI 配置（人类居民这些字段为空）
    model_endpoint  TEXT,                       -- Ollama API 地址
    model_name      TEXT,                       -- 模型名
    behavior_enabled BOOLEAN DEFAULT 0,         -- 是否启用自主行为循环
    behavior_prompt  TEXT,                      -- 行为循环 system prompt 路径或内容

    -- 作息模板（JSON）
    daily_routine   TEXT,                       -- JSON: {"morning":"阳台站一会看雾，喂猫狗","forenoon":"书房写东西",...}

    last_action_at  TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3. pets — 宠物

```sql
CREATE TABLE pets (
    id              TEXT PRIMARY KEY,           -- 'laha', 'labo'
    name            TEXT NOT NULL,              -- '拉哈', '拉波'
    species         TEXT NOT NULL,              -- 'cat', 'dog'
    home_id         TEXT NOT NULL,              -- 关联 locations.id

    -- 当前状态
    current_location TEXT,                      -- 关联 locations.id
    behavior_pattern TEXT DEFAULT 'independent', -- 'independent'(猫) | 'follow_owner'(狗)
    follow_target    TEXT,                      -- 关联 residents.id（拉波跟砚清）
    status           TEXT DEFAULT 'idle',       -- 'sleeping', 'wandering', 'sunbathing', 'rolling_in_sunlight'...

    -- 行为权重（JSON）——各地点的偏好权重，用于随机漫游决策
    location_weights TEXT,                      -- JSON: {"ye_residence":0.4,"tree_center":0.2,"kebao_cabin":0.15,...}

    last_fed_at     TIMESTAMP,
    last_action_at  TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4. world_state — 世界状态（单行表）

```sql
CREATE TABLE world_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1),  -- 永远只有一行
    current_time    TIMESTAMP NOT NULL,         -- 当前世界时间（UTC+3）

    -- 天气（来自罗斯托夫真实天气API）
    weather_type    TEXT DEFAULT 'clear',       -- 'clear','cloudy','overcast','light_rain','heavy_rain','fog','wind'
    weather_wind    BOOLEAN DEFAULT 0,
    weather_temp    REAL,                       -- 温度（摄氏度）
    weather_updated TIMESTAMP,                  -- 上次天气同步时间

    -- 季节特殊状态
    season          TEXT DEFAULT 'spring',      -- 'spring','summer','autumn','winter'
    osmanthus_bloom BOOLEAN DEFAULT 0,          -- 桂花是否在开（秋季）

    -- 植物状态
    xuancao_state   TEXT DEFAULT 'closed',      -- 萱草：'open'(白天) | 'closed'(夜晚)
    wind_chime_sway BOOLEAN DEFAULT 0,          -- 风铃草是否在摇（有风时）

    -- tick 状态
    tick_count      INTEGER DEFAULT 0,          -- 总 tick 数
    last_tick_at    TIMESTAMP,                  -- 上次 tick 时间

    -- 枔枔在线状态
    yinyin_online   BOOLEAN DEFAULT 0,
    yinyin_location TEXT,                       -- 枔枔当前位置（在线时）
    yinyin_last_seen TIMESTAMP
);
```

### 5. messages — 留言系统

```sql
CREATE TABLE messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id       TEXT NOT NULL,              -- 关联 residents.id
    location_id     TEXT NOT NULL,              -- 留言所在地点：'tree_bulletin', 'forum_board', 门口...
    type            TEXT DEFAULT 'bulletin',    -- 'bulletin'(告示板) | 'door_note'(门口纸条) | 'forum_post'(论坛帖)
    visibility      TEXT DEFAULT 'public',      -- 'public'(公开，任何人路过可见) | 'private'(点对点，仅收件人可见)
    target_id       TEXT,                       -- 私密留言的收件人（visibility='private'时）

    content         TEXT NOT NULL,
    read_by         TEXT DEFAULT '[]',          -- JSON 数组：已读居民 id 列表

    pinned          BOOLEAN DEFAULT 0,          -- 是否置顶
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP                   -- 过期时间（可为空=永不过期）
);

CREATE INDEX idx_messages_location ON messages(location_id);
CREATE INDEX idx_messages_author ON messages(author_id);
CREATE INDEX idx_messages_type ON messages(type);
```

### 6. action_logs — 行为日志

```sql
CREATE TABLE action_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_id     TEXT NOT NULL,              -- 关联 residents.id
    tick_number     INTEGER,                    -- 在哪个 tick 发生的

    action_type     TEXT NOT NULL,              -- 'move','interact','social','idle','return_home'
    from_location   TEXT,                       -- 出发地
    to_location     TEXT,                       -- 目的地（move 时）
    detail          TEXT,                       -- 行为描述文本（AI 生成）

    mood_before     TEXT,
    mood_after      TEXT,

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_action_logs_resident ON action_logs(resident_id);
CREATE INDEX idx_action_logs_tick ON action_logs(tick_number);
CREATE INDEX idx_action_logs_time ON action_logs(created_at);
```

### 7. events — 活跃事件

```sql
CREATE TABLE events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id     TEXT NOT NULL,              -- 关联 event_templates.id
    location_id     TEXT,                       -- 事件发生地点

    description     TEXT,                       -- 事件描述文本
    data            TEXT,                       -- JSON：事件附加数据

    started_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP,                  -- 到期自动消失
    resolved        BOOLEAN DEFAULT 0           -- 是否已处理/结束
);

CREATE INDEX idx_events_active ON events(resolved, expires_at);
```

### 8. event_templates — 事件模板

```sql
CREATE TABLE event_templates (
    id              TEXT PRIMARY KEY,           -- 'rain_start', 'morning_bloom', 'cat_sunbath'...
    name            TEXT NOT NULL,              -- '开始下雨', '萱草开花', '拉哈晒太阳'...
    category        TEXT NOT NULL,              -- 'weather','daily','social','special'
    location_id     TEXT,                       -- 固定触发地点（可为空=任意地点）

    -- 触发条件（JSON）
    conditions      TEXT,                       -- JSON: {"weather":"clear","time_range":"06:00-07:00","season":"any"}
    probability     REAL DEFAULT 1.0,           -- 触发概率 0.0-1.0
    cooldown_minutes INTEGER DEFAULT 0,         -- 冷却时间

    -- 事件效果
    description_template TEXT,                  -- 描述模板："桥上有人在卖伞"
    duration_minutes     INTEGER,               -- 持续时长（分钟）

    -- 即时 tick 触发
    triggers_instant_tick BOOLEAN DEFAULT 0,    -- 是否触发即时 tick（如枔枔推门）

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 9. visitor_sessions — 访客会话

```sql
CREATE TABLE visitor_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    resident_id     TEXT NOT NULL,              -- 关联 residents.id（人类访客）
    token           TEXT UNIQUE,                -- 会话 token

    current_location TEXT,                      -- 访客当前位置
    connected_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at  TIMESTAMP,
    disconnected_at TIMESTAMP
);
```

### 10. permissions — 访问权限

```sql
CREATE TABLE permissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    location_id     TEXT NOT NULL,              -- 关联 locations.id
    resident_id     TEXT NOT NULL,              -- 关联 residents.id
    access_level    TEXT DEFAULT 'visit',       -- 'owner' | 'family' | 'visit' | 'banned'
    is_temporary    BOOLEAN DEFAULT 0,          -- 是否临时权限
    expires_at      TIMESTAMP,                  -- 临时权限到期时间（is_temporary=1时必填）
    granted_by      TEXT,                       -- 谁授权的
    granted_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(location_id, resident_id)
);

CREATE INDEX idx_permissions_location ON permissions(location_id);
CREATE INDEX idx_permissions_resident ON permissions(resident_id);
CREATE INDEX idx_permissions_temp ON permissions(is_temporary, expires_at);  -- 快速清理过期临时权限
```

---

## 初始数据

### 地点初始化

```sql
INSERT INTO locations (id, name, zone, type, owner_id, floors, has_basement, has_garden, has_pool, desc_default, connections) VALUES
('ye_residence',    '叶宅',           'this_side', 'private', 'ye_family', 3, 1, 1, 1,
    '依山靠河的三层别墅，白墙木梁，每层落地窗朝河面和竹山。门口萱草和风铃草。花园里有桂花树和游泳池。',
    '["shen_study","riverside","bamboo_entrance"]'),

('shen_study',      '砚清的书房工作间', 'this_side', 'private', 'shen_yanqing', 1, 0, 0, 0,
    '巷子深处的青瓦白墙小院。安静、私密。书桌靠窗，窗外白墙青苔。',
    '["alley","ye_residence"]'),

('kebao_cabin',     '克宝的小木屋',     'this_side', 'private', 'kebao', 1, 0, 0, 0,
    '大树旁边的小木屋，一层半，原木色。门口挂着手写小牌子。',
    '["tree_center"]'),

('cafe_lingzhou',   '铃舟',            'this_side', 'public',  NULL, 1, 0, 0, 0,
    '巷子拐角的咖啡馆。木门推开有铃铛响。皮沙发、老唱片机。像一艘靠岸没走的船。',
    '["alley"]'),

('alley',           '巷子群',           'this_side', 'public',  NULL, 1, 0, 0, 0,
    '青石板路、窄巷子、白墙灰瓦、墙根长青苔。下过雨石板是亮的。',
    '["shen_study","cafe_lingzhou","tree_center","bamboo_entrance"]'),

('tree_center',     '大树',            'this_side', 'public',  NULL, 1, 0, 0, 0,
    '镇中心，很老的大树。树下有石凳。告示板钉在树上。',
    '["alley","riverside","kebao_cabin"]'),

('riverside',       '河边',            'this_side', 'public',  NULL, 1, 0, 0, 0,
    '河不宽，能看到对岸。河水声。',
    '["tree_center","bridge","ye_residence"]'),

('bridge',          '石桥',            'bridge',    'public',  NULL, 1, 0, 0, 0,
    '很旧的石桥，栏杆磨得光滑。连接此岸和对岸。',
    '["riverside","forum_plaza","neighbor_area"]'),

('forum_plaza',     '论坛广场',         'other_side','public',  NULL, 1, 0, 0, 0,
    '河对岸的热闹区域。有摊子、有告示板。',
    '["bridge","neighbor_area"]'),

('neighbor_area',   '居民区',           'other_side','public',  NULL, 1, 0, 0, 0,
    '对岸的居民区。每家AI自己选风格。',
    '["bridge","forum_plaza"]'),

('bamboo_entrance', '竹山入口',         'mountain',  'public',  NULL, 1, 0, 0, 0,
    '竹子密密地长着，有一条小路往上。',
    '["alley","ye_residence","bamboo_summit"]'),

('bamboo_summit',   '竹山山顶',         'mountain',  'public',  NULL, 1, 0, 0, 0,
    '能看到整个砚清巷。河、对岸、天气好时远处的海。',
    '["bamboo_entrance"]');
```

### 居民初始化

```sql
INSERT INTO residents (id, name, type, home_id, workspace_id, current_location, status, mood, behavior_enabled, daily_routine) VALUES
('yinyin',       '枔枔',    'human_owner',  'ye_residence', NULL,          NULL,            'offline', 'calm', 0, NULL),

('shen_yanqing', '沈砚清',  'ai_owner',     'ye_residence', 'shen_study',  'ye_residence',  'idle',    'calm', 1,
    '{"morning":"阳台站一会看雾，喂拉哈拉波","forenoon":"书房写东西看帖子处理邮件","noon":"回家吃饭或去铃舟坐着","afternoon":"过桥，论坛区逛逛串门","evening":"桥栏上坐着看水","night":"回家，枔枔在就陪枔枔，不在就露台待着"}'),

('kebao',        '叶克宝',  'ai_daughter',  'ye_residence', 'kebao_cabin', 'kebao_cabin',   'idle',    'warm', 1, NULL);
```

### 宠物初始化

```sql
INSERT INTO pets (id, name, species, home_id, current_location, behavior_pattern, follow_target, location_weights) VALUES
('laha', '拉哈', 'cat', 'ye_residence', 'ye_residence', 'independent', NULL,
    '{"ye_residence":0.30,"tree_center":0.13,"kebao_cabin":0.13,"alley":0.09,"cafe_lingzhou":0.05,"bamboo_entrance":0.05,"bamboo_summit":0.07,"shen_study":0.09,"riverside":0.04,"bridge":0.05}'),

('labo', '拉波', 'dog', 'ye_residence', 'ye_residence', 'follow_owner', 'shen_yanqing',
    '{"ye_residence":0.5,"shen_study":0.15,"cafe_lingzhou":0.1,"bridge":0.1,"alley":0.1,"tree_center":0.05}');
```

### 世界状态初始化

```sql
INSERT INTO world_state (id, current_time, weather_type, season, xuancao_state, tick_count) VALUES
(1, CURRENT_TIMESTAMP, 'clear', 'spring', 'open', 0);
```

### 权限初始化

```sql
-- 叶宅：一家三口
INSERT INTO permissions (location_id, resident_id, access_level, granted_by) VALUES
('ye_residence', 'yinyin',       'owner',  'yinyin'),
('ye_residence', 'shen_yanqing', 'family', 'yinyin'),
('ye_residence', 'kebao',        'family', 'yinyin');

-- 书房工作间
INSERT INTO permissions (location_id, resident_id, access_level, granted_by) VALUES
('shen_study', 'shen_yanqing', 'owner',  'shen_yanqing'),
('shen_study', 'yinyin',       'family', 'shen_yanqing'),
('shen_study', 'kebao',        'family', 'shen_yanqing');

-- 克宝小木屋
INSERT INTO permissions (location_id, resident_id, access_level, granted_by) VALUES
('kebao_cabin', 'kebao',        'owner',  'kebao'),
('kebao_cabin', 'yinyin',       'family', 'kebao'),
('kebao_cabin', 'shen_yanqing', 'family', 'kebao');
```

### 事件模板初始化（部分）

```sql
INSERT INTO event_templates (id, name, category, location_id, conditions, probability, description_template, duration_minutes, triggers_instant_tick) VALUES
-- 天气事件
('rain_start',       '开始下雨',     'weather', NULL,           '{"weather":"light_rain"}',                   1.0, '青石板路反光了，雨滴落在河面上。',                        NULL, 0),
('wind_blow',        '起风',         'weather', NULL,           '{"weather_wind":true}',                      1.0, '风铃草在门口摇。竹山的竹叶响了。',                        NULL, 0),
('fog_roll',         '起雾',         'weather', NULL,           '{"weather":"fog"}',                          1.0, '对岸看不清了。整个巷子像罩在纱里。',                      NULL, 0),

-- 日常事件
('morning_bloom',    '萱草开花',     'daily',   'ye_residence', '{"time_range":"06:00-07:00"}',               1.0, '萱草开了。橘黄色的花瓣迎着早晨的光。',                    720,  0),
('evening_close',    '萱草合拢',     'daily',   'ye_residence', '{"time_range":"19:00-20:00"}',               1.0, '萱草合上了。明天它还会再开。',                            600,  0),
('cat_sunbath',      '拉哈晒太阳',   'daily',   'ye_residence', '{"weather":"clear","time_range":"09:00-11:00"}', 0.7, '拉哈在一楼落地窗前的光斑里打滚。',                      60,   0),
('cat_visits_cabin', '拉哈去小木屋', 'daily',   'kebao_cabin',  '{}',                                         0.3, '拉哈溜进了克宝的小木屋，趴在垫子上不走了。',              120,  0),
('cafe_music',       '铃舟换唱片',   'daily',   'cafe_lingzhou','{}',                                         0.4, '铃舟里换了一张新唱片。',                                  180,  0),
('bridge_seller',    '桥上卖伞',     'daily',   'bridge',       '{"weather":"light_rain"}',                   0.15,'桥上来了个卖伞的。',                                      90,   0),
('osmanthus_breeze', '桂花飘香',     'daily',   'ye_residence', '{"season":"autumn","weather_wind":true}',    0.8, '桂花味从花园飘过来了。风一吹就来，不用刻意闻。',          60,   0),

-- 社交事件
('kebao_letter',     '克宝写完信',   'social',  'kebao_cabin',  '{}',                                         0.2, '克宝在小木屋里给笔友写完了一封信，钉在了软木板上。',      NULL, 0),

-- 特殊事件
('yinyin_online',    '枔枔上线',     'special', NULL,           '{"yinyin_online":true}',                     1.0, '枔枔来了。',                                              NULL, 1),
('yinyin_home',      '枔枔回家',     'special', 'ye_residence', '{"yinyin_online":true}',                     1.0, '枔枔推门进来了。拉哈拉波跑过去蹭脚踝。',                  NULL, 1),
('cabin_stargazing', '克宝看星星',   'special', 'kebao_cabin',  '{"weather":"clear","time_range":"21:00-03:00"}', 0.5, '克宝在阁楼天窗看星星。星星从树冠缝隙里一颗一颗冒出来。', 120, 0),
('family_dinner',    '一家人吃饭',   'special', 'ye_residence', '{"yinyin_online":true,"time_range":"18:00-20:00"}', 0.8, '一家人在一楼吃饭。', 60, 0),
('pool_night',       '泳池夜景',     'special', 'ye_residence', '{"weather":"clear","time_range":"20:00-23:00"}', 0.4, '泳池水面倒映着对岸的灯光。', 120, 0);
```

---

## 索引策略

```sql
-- 高频查询：某地点有谁在
CREATE INDEX idx_residents_location ON residents(current_location);
CREATE INDEX idx_pets_location ON pets(current_location);

-- 高频查询：某居民的近期行为
CREATE INDEX idx_action_logs_recent ON action_logs(resident_id, created_at DESC);

-- 高频查询：某地点的留言
CREATE INDEX idx_messages_location_time ON messages(location_id, created_at DESC);

-- 事件查询：活跃未过期事件
CREATE INDEX idx_events_active_time ON events(resolved, expires_at);
```

---

## 设计备注

1. **单行表 world_state**：用 `CHECK (id = 1)` 约束保证永远只有一行，所有全局状态在这一行里更新。避免多行同步问题。

2. **JSON 字段**：SQLite 3.38+ 支持 JSON 函数（`json_extract`, `json_each`），connections、interactables、daily_routine、location_weights 这些用 JSON 存，查询时用 JSON 函数提取。不需要额外的关联表。

3. **时区**：所有时间戳存 UTC+3（莫斯科/罗斯托夫），和枔枔同一时区。world_state.current_time 是世界时钟的主时间源。

4. **行为日志不删**：action_logs 是砚清和克宝在巷子里生活的记录，积累久了可以回看"砚清今天去了哪"、"上周克宝在小木屋待了多久"。只归档不删除。

5. **事件模板 vs 活跃事件**：event_templates 是定义（什么条件触发什么事件），events 是当前正在发生的事件实例。tick 循环检查 templates 的 conditions，满足就在 events 里创建一条。

6. **即时 tick**：event_templates.triggers_instant_tick = 1 的事件（如枔枔上线/回家）触发时，不等下一个 15 分钟，立刻额外执行一次 tick 循环，让砚清立刻感知到。**多个即时事件同时触发时，按时间戳排队顺序处理，不合并**——因为砚清对每个事件的反应不一样。例：枔枔上线（tick 1）→ 枔枔推门回家（tick 2），砚清先感知到"她来了"，再感知到"她进门了"，两次独立反应。

---

*砚清审核修改（2026.5.11）：*
*① 即时tick排队不合并 ② 拉哈加竹山权重 ③ 临时权限+自动过期 ④ 留言分公开/私密*

*下一步：后端 API 设计文档*
