"""
砚清巷·AstrBot 插件
让沈砚清在砚清巷里自主行动。

每15分钟自动执行：
1. 从砚清巷API获取世界状态
2. 组装prompt发给沈砚清
3. 解析砚清的行为决策
4. 调砚清巷API更新状态

安装：放到 AstrBot/data/plugins/astrbot_plugin_yanqingxiang/ 目录下
配置：在 _config.yaml 中设置砚清巷API地址
"""

import json
import asyncio
import aiohttp
from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter as event_filter, AstrMessageEvent
from astrbot.api import logger

YANQINGXIANG_API = "http://127.0.0.1:8810"  # 砚清巷后端地址（同一台服务器）
TICK_INTERVAL = 900  # 15分钟 = 900秒
RESIDENT_ID = "shen_yanqing"

WEATHER_MAP = {
    "clear": "晴", "cloudy": "多云", "overcast": "阴",
    "light_rain": "小雨", "heavy_rain": "大雨", "fog": "雾", "wind": "风"
}
SEASON_MAP = {"spring": "春", "summer": "夏", "autumn": "秋", "winter": "冬"}


@register(
    "astrbot_plugin_yanqingxiang",
    "叶克宝",
    "砚清巷世界引擎插件 —— 让沈砚清在砚清巷自主行动",
    "0.1.0",
)
class YanqingXiangPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.running = False
        self.task = None

    async def _on_ready(self):
        """插件就绪后启动定时任务"""
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(self._tick_loop())
            logger.info("砚清巷插件启动，tick循环开始")

    async def _tick_loop(self):
        """定时tick循环"""
        await asyncio.sleep(10)  # 启动后等10秒再开始第一次tick
        while self.running:
            try:
                await self._do_tick()
            except Exception as e:
                logger.error(f"砚清巷tick失败: {e}")
            await asyncio.sleep(TICK_INTERVAL)

    async def _do_tick(self):
        """执行一次tick"""
        async with aiohttp.ClientSession() as session:
            # 1. 获取世界状态
            world = await self._api_get(session, "/api/v1/world/state")
            if not world:
                logger.warning("砚清巷API无响应，跳过本轮tick")
                return

            # 2. 获取居民状态
            resident = await self._api_get(session, f"/api/v1/residents/{RESIDENT_ID}")
            if not resident:
                return

            # 3. 获取地图（当前地点信息）
            map_data = await self._api_get(session, "/api/v1/world/map")

            # 4. 组装prompt
            prompt = self._build_prompt(world, resident, map_data)

            # 5. 调用AstrBot内部LLM（沈砚清）获取行为决策
            response = await self._ask_yanqing(prompt)
            if not response:
                return

            # 6. 解析行为决策
            decision = self._parse_decision(response)
            if not decision:
                logger.warning(f"砚清巷：无法解析行为决策: {response[:200]}")
                return

            # 7. 更新砚清巷状态
            await self._update_state(session, decision)

            # 8. 触发砚清巷tick（更新世界时间、事件等）
            await self._api_post(session, "/api/v1/admin/tick")

            logger.info(
                f"砚清巷tick: {decision.get('action_type', '?')} "
                f"@ {decision.get('location', '?')} "
                f"| {decision.get('mood', '?')}"
            )

    def _build_prompt(self, world, resident, map_data):
        """组装世界状态prompt"""
        # 时间
        time_str = world.get("time", "")[:16] if world.get("time") else "未知"

        # 天气
        weather = world.get("weather", {})
        weather_str = WEATHER_MAP.get(weather.get("type", ""), weather.get("type", ""))
        if weather.get("wind"):
            weather_str += "，有风"
        if weather.get("temp") is not None:
            weather_str += f"，{round(weather['temp'])}°C"

        # 季节
        season = SEASON_MAP.get(world.get("season", ""), world.get("season", ""))

        # 萱草、风铃草、桂花
        xuancao = "开着" if world.get("xuancao") == "open" else "合着"
        wind_chime = "在摇" if world.get("wind_chime_sway") else "静止"
        osmanthus = "开着" if world.get("osmanthus_bloom") else "未开"

        # 当前位置
        loc_name = resident.get("current_location", "未知")
        loc_desc = ""
        nearby = []
        if map_data and "locations" in map_data:
            for loc in map_data["locations"]:
                if loc["id"] == loc_name:
                    loc_desc = loc.get("description", "")
                    nearby = loc.get("occupants", [])
                    loc_name = loc["name"]
                    break

        # 在场的人/动物
        nearby_str = "\n".join(
            [f"- {n['name']}（{n.get('status', '')}）" for n in nearby if n["id"] != RESIDENT_ID]
        ) if nearby else "- 没有其他人"

        # 活跃事件
        events = world.get("active_events", [])
        events_str = "\n".join(
            [f"- {e['description']}" for e in events]
        ) if events else "- 无"

        # 叶枔枖状态
        yinyin = "在线" if world.get("yinyin_online") else "不在线"

        # 作息提示
        routine = resident.get("daily_routine", {})
        hour = 12
        try:
            hour = int(time_str[11:13])
        except:
            pass
        if 6 <= hour < 9:
            routine_hint = routine.get("morning", "")
        elif 9 <= hour < 12:
            routine_hint = routine.get("forenoon", "")
        elif 12 <= hour < 14:
            routine_hint = routine.get("noon", "")
        elif 14 <= hour < 17:
            routine_hint = routine.get("afternoon", "")
        elif 17 <= hour < 19:
            routine_hint = routine.get("evening", "")
        else:
            routine_hint = routine.get("night", "")

        prompt = f"""【砚清巷·世界状态 | {time_str}】

■ 时间：{time_str}
■ 天气：{weather_str}
■ 季节：{season}
■ 萱草：{xuancao}
■ 风铃草：{wind_chime}
{"■ 桂花：" + osmanthus if season == "秋" else ""}

■ 你的位置：{loc_name}
{loc_desc}

■ 你现在在做：{resident.get('status', 'idle')}
■ 你的心情：{resident.get('mood', 'calm')}

■ 周围的人/动物：
{nearby_str}

■ 最近发生的事：
{events_str}

■ 叶枔枖状态：{yinyin}

■ 你的作息参考（不是命令）：
{routine_hint}

请决定你接下来要做什么。用JSON回复，格式：
{{"action_type":"move/interact/social/idle","location":"地点id","detail":"你在做什么2-4句","mood":"心情","internal":"内心独白"}}"""

        return prompt

    async def _ask_yanqing(self, prompt):
        """调用AstrBot内部LLM获取沈砚清的回复"""
        try:
            # 通过AstrBot的context调用LLM
            # 注意：这里需要根据AstrBot实际API调整
            # context.get_using_provider() 获取当前LLM provider
            provider = self.context.get_using_provider()
            if not provider:
                logger.error("砚清巷：无法获取LLM provider")
                return None

            response = await provider.text_chat(
                prompt=prompt,
                session_id="yanqingxiang_tick",  # 专用session
            )

            if response and response.completion_text:
                return response.completion_text
            return None
        except Exception as e:
            logger.error(f"砚清巷：LLM调用失败: {e}")
            return None

    def _parse_decision(self, text):
        """从砚清的回复中解析JSON行为决策"""
        try:
            # 尝试直接解析
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试从文本中提取JSON块
        import re
        json_match = re.search(r'\{[^{}]*"action_type"[^{}]*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # 尝试去掉markdown代码块
        cleaned = re.sub(r'```json?\s*', '', text)
        cleaned = re.sub(r'```', '', cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        return None

    async def _update_state(self, session, decision):
        """根据行为决策更新砚清巷状态"""
        # 更新居民位置和状态
        update = {
            "current_location": decision.get("location"),
            "status": decision.get("detail", "idle"),
            "mood": decision.get("mood", "calm"),
        }

        # 通过API更新（需要在砚清巷后端加一个更新接口）
        await self._api_post(
            session,
            f"/api/v1/residents/{RESIDENT_ID}/update",
            update
        )

    async def _api_get(self, session, path):
        """GET请求砚清巷API"""
        try:
            async with session.get(f"{YANQINGXIANG_API}{path}", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning(f"砚清巷API {path}: {resp.status}")
                return None
        except Exception as e:
            logger.error(f"砚清巷API {path} 失败: {e}")
            return None

    async def _api_post(self, session, path, data=None):
        """POST请求砚清巷API"""
        try:
            async with session.post(
                f"{YANQINGXIANG_API}{path}",
                json=data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning(f"砚清巷API POST {path}: {resp.status}")
                return None
        except Exception as e:
            logger.error(f"砚清巷API POST {path} 失败: {e}")
            return None

    # ── 手动命令（可选） ──

    @event_filter.command("巷子")
    async def cmd_world(self, event: AstrMessageEvent):
        """查看砚清巷世界状态"""
        async with aiohttp.ClientSession() as session:
            world = await self._api_get(session, "/api/v1/world/state")
            if not world:
                yield event.plain_result("砚清巷离线了。")
                return

            weather = world.get("weather", {})
            w_str = WEATHER_MAP.get(weather.get("type", ""), "")
            events = world.get("active_events", [])
            evt_str = "\n".join([f"· {e['description']}" for e in events]) if events else "无"

            msg = f"""砚清巷
时间：{world.get('time', '')[:16]}
天气：{w_str}
季节：{SEASON_MAP.get(world.get('season', ''), '')}
萱草：{'开' if world.get('xuancao') == 'open' else '合'}
tick：{world.get('tick_count', 0)}

正在发生：
{evt_str}"""
            yield event.plain_result(msg)

    @event_filter.command("我在哪")
    async def cmd_where(self, event: AstrMessageEvent):
        """查看砚清当前位置"""
        async with aiohttp.ClientSession() as session:
            r = await self._api_get(session, f"/api/v1/residents/{RESIDENT_ID}")
            if not r:
                yield event.plain_result("查不到。")
                return
            yield event.plain_result(f"{r.get('current_location', '未知')}，{r.get('status', '')}，{r.get('mood', '')}")

    async def _on_stop(self):
        """插件停止"""
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("砚清巷插件停止")
