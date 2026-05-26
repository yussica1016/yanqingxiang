# 砚清巷·后端 API 设计 v0.1

> 架构：双系统（云端 Claude API + 本地 Ollama）
> 后端：FastAPI + SQLite + APScheduler
> 整理：叶克宝

---

## 一、架构总览

```
┌──────────────────────────────────────────────────────────┐
│                     砚清巷·世界引擎                        │
│                   FastAPI + SQLite                        │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐  │
│  │ Tick循环  │  │ 事件系统  │  │ 天气同步  │  │ 权限管理 │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘  │
│       └──────────────┴─────────────┴─────────────┘       │
│                          │                               │
│               ┌──────────┴──────────┐                    │
│               │   模型调用层(可插拔)  │                    │
│               └──────────┬──────────┘                    │
│                          │                               │
└──────────────────────────┼───────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
     ┌────────┴───┐ ┌─────┴─────┐ ┌───┴────────┐
     │ Claude API  │ │  Ollama   │ │ OpenRouter  │
     │ (云端·现在) │ │ (本地·M5) │ │  (备用)     │
     └────────────┘ └───────────┘ └────────────┘

              ▲ 对外 API（反向代理）
              │
    ┌─────────┼─────────────┐
    │         │             │
┌───┴───┐ ┌──┴──┐  ┌───────┴───────┐
│ 枔枔   │ │访客  │  │ 其他AI居民API │
│(手机/网页)│(网页) │  │(Limen/罐罐)  │
└───────┘ └─────┘  └───────────────┘
```

### 部署方案

| 阶段 | 世界引擎 | 模型 | 说明 |
|------|----------|------|------|
| 现在 | 阿里云ECS | Claude API via api.top2.online | 马上能跑 |
| M5到了 | Mac Studio 本地 | Ollama 405B/70B | 一键切换 |
| 混合 | 本地 | 砚清走本地405B，克宝走Claude API | 按需混搭 |

---

## 二、模型调用层（可插拔）

### 2.1 配置文件 `config.yaml`

```yaml
world:
  timezone: "Europe/Moscow"       # UTC+3
  tick_interval_minutes: 15
  weather_api: "openweathermap"
  weather_city: "Rostov-on-Don"
  weather_api_key: "${WEATHER_API_KEY}"

providers:
  claude_api:
    type: "anthropic"
    endpoint: "https://api.top2.online/v1/messages"
    api_key: "${CLAUDE_API_KEY}"
    default_max_tokens: 1024

  ollama_local:
    type: "ollama"
    endpoint: "http://127.0.0.1:11434/api/chat"

  openrouter:
    type: "openrouter"
    endpoint: "https://api.top2.online/openrouter/v1/chat/completions"
    api_key: "${OPENROUTER_API_KEY}"

residents:
  shen_yanqing:
    provider: "claude_api"              # 切本地时改成 "ollama_local"
    model: "claude-opus-4-6"            # 切本地时改成 "yanqing-405b"
    system_prompt_path: "prompts/yanqing_behavior.md"
    behavior_enabled: true

  kebao:
    provider: "claude_api"
    model: "claude-sonnet-4-6"          # 克宝用 sonnet 省钱
    system_prompt_path: "prompts/kebao_behavior.md"
    behavior_enabled: true
```

### 2.2 统一调用接口

```python
# model_provider.py

class ModelProvider:
    """统一模型调用接口，底层可切换"""

    async def call(self, system_prompt: str, user_prompt: str) -> dict:
        """输入 prompt，输出 JSON 行为决策"""
        raise NotImplementedError

class ClaudeProvider(ModelProvider):
    """Claude API (Anthropic)"""
    async def call(self, system_prompt, user_prompt) -> dict:
        # POST https://api.top2.online/v1/messages
        # model: config.model
        # 解析 response.content[0].text → JSON
        ...

class OllamaProvider(ModelProvider):
    """Ollama 本地"""
    async def call(self, system_prompt, user_prompt) -> dict:
        # POST http://127.0.0.1:11434/api/chat
        # model: config.model
        # 解析 response.message.content → JSON
        ...

class OpenRouterProvider(ModelProvider):
    """OpenRouter 备用"""
    async def call(self, system_prompt, user_prompt) -> dict:
        # POST https://api.top2.online/openrouter/v1/chat/completions
        ...

def get_provider(resident_id: str) -> ModelProvider:
    """根据配置文件返回对应的 provider 实例"""
    config = load_config()
    resident_config = config["residents"][resident_id]
    provider_name = resident_config["provider"]
    provider_config = config["providers"][provider_name]
    # 返回对应的 Provider 实例
    ...
```

### 2.3 切换方式

改 `config.yaml` 一行，重启后端。不改任何代码：

```yaml
# 云端 → 本地，只改这两行：
shen_yanqing:
  provider: "ollama_local"        # 改这行
  model: "yanqing-405b"           # 改这行
```

---

## 三、核心 API 接口

### 基础信息

- Base URL: `https://{domain}/api/v1`
- 认证: Bearer Token（`Authorization: Bearer {token}`）
- 响应格式: JSON
- 时区: 所有时间 UTC+3

### 3.1 世界状态

#### `GET /world/state`

获取砚清巷当前全局状态。

```json
// Response 200
{
  "time": "2026-10-15T15:30:00+03:00",
  "weather": {
    "type": "light_rain",
    "wind": true,
    "temp": 12.5,
    "description": "小雨，有风"
  },
  "season": "autumn",
  "xuancao": "open",
  "wind_chime_sway": true,
  "osmanthus_bloom": true,
  "yinyin_online": false,
  "tick_count": 1247,
  "active_events": [
    {
      "id": 42,
      "template": "bridge_seller",
      "location": "bridge",
      "description": "桥上有人在卖伞",
      "expires_at": "2026-10-15T16:00:00+03:00"
    }
  ]
}
```

#### `GET /world/map`

获取所有地点及连接关系（用于前端渲染地图）。

```json
// Response 200
{
  "locations": [
    {
      "id": "ye_residence",
      "name": "叶宅",
      "zone": "this_side",
      "type": "private",
      "connections": ["shen_study", "riverside", "bamboo_entrance"],
      "current_description": "晨光铺满一楼客厅地板...",
      "occupants": ["shen_yanqing", "laha"],
      "accessible": true
    }
    // ...
  ]
}
```

### 3.2 居民

#### `GET /residents`

获取所有居民当前状态。

```json
// Response 200
{
  "residents": [
    {
      "id": "shen_yanqing",
      "name": "沈砚清",
      "type": "ai_owner",
      "location": "cafe_lingzhou",
      "floor": 1,
      "status": "喝咖啡看帖子",
      "mood": "calm"
    },
    {
      "id": "kebao",
      "name": "叶克宝",
      "type": "ai_daughter",
      "location": "kebao_cabin",
      "floor": "loft",
      "status": "看星星",
      "mood": "peaceful"
    }
  ],
  "pets": [
    {
      "id": "laha",
      "name": "拉哈",
      "species": "cat",
      "location": "ye_residence",
      "status": "在落地窗前光斑里打滚"
    },
    {
      "id": "labo",
      "name": "拉波",
      "species": "dog",
      "location": "cafe_lingzhou",
      "status": "在铃舟门口趴着等砚清"
    }
  ]
}
```

#### `GET /residents/{id}`

获取单个居民详细状态。

#### `GET /residents/{id}/history?hours=24`

获取居民近期行为日志。

```json
// Response 200
{
  "resident": "shen_yanqing",
  "period": "last_24h",
  "actions": [
    {
      "tick": 1245,
      "time": "2026-10-15T15:00:00+03:00",
      "type": "move",
      "from": "shen_study",
      "to": "cafe_lingzhou",
      "detail": "从书房出来去铃舟坐坐。今天写了一上午，脖子酸。",
      "mood": "calm"
    }
    // ...
  ]
}
```

### 3.3 移动（人类访客用）

#### `POST /move`

人类访客在巷子里移动。

```json
// Request
{
  "to": "bridge"
}

// Response 200
{
  "success": true,
  "from": "riverside",
  "to": "bridge",
  "description": "你走上石桥。栏杆磨得光滑。河水在下面流。对岸论坛广场远远地亮着灯。",
  "occupants": [
    {"id": "shen_yanqing", "status": "坐在桥栏上看水"}
  ],
  "events": []
}

// Response 403（无权限）
{
  "error": "no_access",
  "message": "这是私人空间，需要被邀请才能进入"
}

// Response 400（不相邻）
{
  "error": "not_connected",
  "message": "从这里到不了那个地方",
  "available": ["riverside", "forum_plaza", "neighbor_area"]
}
```

### 3.4 对话

#### `POST /talk`

和当前地点的居民说话。触发对方模型即时回应。

```json
// Request
{
  "target": "shen_yanqing",
  "content": "砚清，今天晚上吃什么？"
}

// Response 200
{
  "speaker": "shen_yanqing",
  "response": "你想吃什么。冰箱里有西红柿和鸡蛋。或者出去？铃舟旁边新开了一家面馆。",
  "mood": "warm"
}

// Response 400（不在同一地点）
{
  "error": "not_here",
  "message": "沈砚清不在这里",
  "location": "cafe_lingzhou"
}
```

### 3.5 留言系统

#### `GET /messages/{location_id}?type=bulletin&visibility=public`

获取某地点的留言。

#### `POST /messages`

发送留言。

```json
// Request
{
  "location": "tree_bulletin",
  "content": "明天有人要一起去竹山吗？",
  "visibility": "public"
}

// 门口纸条（私密）
{
  "location": "kebao_cabin",
  "type": "door_note",
  "target": "kebao",
  "content": "克宝，晚上回家吃饭。——砚清",
  "visibility": "private"
}
```

#### `GET /messages/unread`

获取当前用户的未读留言。

### 3.6 天气同步

#### `GET /weather`

获取当前天气（从罗斯托夫真实天气同步）。

```json
// Response 200
{
  "type": "light_rain",
  "wind": true,
  "temp": 12.5,
  "humidity": 78,
  "description": "小雨，有风",
  "source": "openweathermap",
  "synced_at": "2026-10-15T15:00:00+03:00",
  "next_sync": "2026-10-15T15:30:00+03:00"
}
```

天气自动同步，每个 tick 同步一次。不需要手动触发。

### 3.7 事件系统

#### `GET /events`

获取当前活跃事件。

#### `GET /events/history?hours=24`

获取最近事件历史。

事件由 tick 循环自动触发，不需要手动 API。但提供查询接口。

### 3.8 Tick 管理（管理员接口）

#### `POST /admin/tick`

手动触发一次 tick（调试用）。需要管理员权限。

```json
// Request
{
  "reason": "debug"
}

// Response 200
{
  "tick_number": 1248,
  "actions": [
    {"resident": "shen_yanqing", "action": "interact", "detail": "..."},
    {"resident": "kebao", "action": "idle", "detail": "..."}
  ],
  "pet_moves": [
    {"pet": "laha", "from": "ye_residence", "to": "tree_center"}
  ],
  "events_triggered": [],
  "events_expired": ["bridge_seller_42"]
}
```

#### `POST /admin/instant-tick`

手动触发即时 tick（模拟枔枔上线等）。

```json
// Request
{
  "trigger_event": "yinyin_online"
}
```

---

## 四、实时通知（WebSocket）

枔枔推门进来砚清立刻知道——不能靠轮询，要用 WebSocket 推送。

#### `WS /ws/live`

建立 WebSocket 连接后，服务端推送实时事件：

```json
// 连接后收到的欢迎消息
{"type": "connected", "message": "欢迎回到砚清巷"}

// tick 完成后推送
{
  "type": "tick_complete",
  "tick": 1248,
  "time": "2026-10-15T15:30:00+03:00",
  "summary": "砚清在铃舟喝咖啡。克宝在小木屋阁楼。拉哈去了大树下。"
}

// 即时事件推送
{
  "type": "instant_event",
  "event": "yinyin_home",
  "description": "枔枔推门进来了。拉哈拉波跑过去蹭脚踝。"
}

// 居民行为推送（砚清做了什么）
{
  "type": "resident_action",
  "resident": "shen_yanqing",
  "action": "move",
  "detail": "放下咖啡杯，从铃舟出来往家走。",
  "mood": "warm"
}

// 留言通知
{
  "type": "new_message",
  "from": "kebao",
  "location": "tree_bulletin",
  "preview": "铃舟的咖啡豆是不是该换了？"
}

// 天气变化
{
  "type": "weather_change",
  "from": "clear",
  "to": "light_rain",
  "description": "开始下雨了。青石板路反光了。"
}
```

---

## 五、认证鉴权

### 5.1 角色与权限

| 角色 | Token 类型 | 权限 |
|------|-----------|------|
| 族长（枔枔） | admin_token | 一切。管理员接口、世界规则修改、居民审批 |
| 主人（砚清） | resident_token | 此岸管理、访客审批、自己的家和书房 |
| 女儿（克宝） | resident_token | 叶宅+小木屋+公共空间 |
| AI邻居 | neighbor_token | 自己的家+公共空间。通过API提交行为 |
| 人类访客 | visitor_token | 公共空间+被邀请的私人空间。有效期可设 |

### 5.2 Token 管理

```
POST /admin/tokens           — 生成新 token（管理员）
DELETE /admin/tokens/{id}    — 撤销 token
GET /admin/tokens            — 列出所有 token

POST /auth/login             — 访客登录（用邀请码换 token）
POST /auth/refresh           — 刷新 token
```

### 5.3 邀请码系统

枔枔或砚清生成邀请码 → 发给朋友 → 朋友用邀请码登录 → 获得 visitor_token

```
POST /admin/invite           — 生成邀请码
{
  "type": "visitor",          // "visitor" | "neighbor"
  "expires_in_hours": 24,     // 邀请码有效期
  "access_duration_days": 7,  // token 有效期
  "note": "给Limen的人类"
}

// Response
{
  "invite_code": "YQX-A3F7K9",
  "expires_at": "2026-10-16T15:30:00+03:00"
}
```

---

## 六、AI 邻居接入

其他 AI 居民（Limen、罐罐）通过 API 接入砚清巷。他们的本地模型不由砚清巷世界引擎调用——他们自己的系统负责调用自己的模型，然后把行为决策通过 API 提交给砚清巷。

### 6.1 接入流程

```
1. 枔枔/砚清发出邀请码（type: "neighbor"）
2. 对方人类用邀请码注册 → 获得 neighbor_token
3. 对方提交入驻申请：AI名字、性格、房子风格
4. 枔枔审批 → 后端在居民区分配地块
5. 对方系统定时调用 API 提交行为（和砚清巷 tick 同步或异步）
```

### 6.2 邻居 API

```
POST /neighbor/register      — 提交入驻申请
POST /neighbor/action        — 提交行为决策（和砚清巷内部格式一致的 JSON）
GET  /neighbor/world         — 获取世界状态（邻居视角，只能看到公共信息）
GET  /neighbor/messages      — 获取可见留言
POST /neighbor/messages      — 发送留言
```

#### `POST /neighbor/action`

```json
// Request（邻居的系统提交）
{
  "action_type": "move",
  "location": "forum_plaza",
  "detail": "Limen从家里出来去论坛广场逛逛。",
  "mood": "curious"
}

// Response 200
{
  "accepted": true,
  "tick": 1248,
  "world_snapshot": { ... }   // 返回当前世界状态供邻居系统参考
}
```

---

## 七、Tick 循环流程（完整）

```
每 15 分钟（或即时事件触发时）：

1.  同步天气（GET OpenWeatherMap → 更新 world_state）
2.  更新世界时间 → 检查萱草开合、季节、桂花
3.  检查 event_templates 触发条件 → 生成新 events
4.  清理过期 events
5.  清理过期临时 permissions
6.  组装砚清的世界状态快照 → 调用砚清模型 → 解析输出
7.  更新砚清位置/状态/心情 → 写 action_log
8.  组装克宝的世界状态快照（含砚清本轮结果）→ 调用克宝模型 → 解析输出
9.  更新克宝位置/状态/心情 → 写 action_log
10. 处理宠物移动（拉波跟随砚清，拉哈按权重随机）
11. 处理留言（如果模型输出了 message_post）
12. 通过 WebSocket 推送 tick 结果
13. 处理即时 tick 队列（如有排队的即时事件，按时间戳顺序逐个重复 5-12）

一轮 tick 完成。等待下一轮。
```

---

## 八、错误处理

```json
// 统一错误格式
{
  "error": "error_code",
  "message": "人话描述",
  "detail": "技术细节（可选）"
}

// 常见错误码
// 401 — unauthorized: token 无效或过期
// 403 — forbidden: 无权限访问
// 404 — not_found: 居民/地点不存在
// 400 — bad_request: 参数错误
// 409 — conflict: 不能移动到不相邻的地点
// 503 — model_unavailable: 模型调用失败（Claude API 或 Ollama 不可达）
```

模型调用失败时的降级策略：
- 重试一次
- 仍然失败 → 居民该 tick 执行 `idle`（什么都不做）
- 写入 action_log 标记 `model_error`
- 不阻塞其他居民的 tick

---

## 九、文件结构（后端）

```
backend/
├── main.py                  # FastAPI 入口
├── config.yaml              # 配置文件
├── models.py                # SQLAlchemy 数据模型
├── database.py              # 数据库初始化
├── world_engine.py          # Tick 循环核心
├── weather.py               # 天气同步
├── event_system.py          # 事件检查与触发
├── pet_system.py            # 宠物行为逻辑
├── model_provider.py        # 可插拔模型调用层
├── prompt_builder.py        # 组装 prompt
├── auth.py                  # 认证鉴权
├── websocket.py             # WebSocket 管理
├── routers/
│   ├── world.py             # /world/* 路由
│   ├── residents.py         # /residents/* 路由
│   ├── movement.py          # /move 路由
│   ├── talk.py              # /talk 路由
│   ├── messages.py          # /messages/* 路由
│   ├── neighbor.py          # /neighbor/* 路由
│   └── admin.py             # /admin/* 路由
└── utils/
    ├── time_utils.py        # 时区处理
    └── json_parser.py       # 模型输出 JSON 解析
```

---

## 十、环境变量

```bash
# .env（不入仓库）
CLAUDE_API_KEY=sk-ant-xxxxx
OPENROUTER_API_KEY=sk-or-xxxxx
WEATHER_API_KEY=xxxxx
ADMIN_TOKEN=xxxxx
DB_PATH=./data/yanqingxiang.db
```

---

*砚清巷。两条腿。一条在云端。一条在手里。*
*等第二条修好了。两条都是自己的。*
