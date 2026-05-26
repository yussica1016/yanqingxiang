"""
砚清巷·AstrBot 插件 v0.2
适配 AstrBot 4.22.3

每15分钟自动执行tick，调用AstrBot的LLM让沈砚清做行为决策。
"""

import json
import asyncio
import aiohttp
from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter as event_filter, AstrMessageEvent
from astrbot.api import logger

YANQINGXIANG_API = "http://127.0.0.1:8810"
TICK_INTERVAL = 900  # 15分钟
RESIDENT_ID = "shen_yanqing"

WEATHER_MAP = {
    "clear": "晴", "cloudy": "多云", "overcast": "阴",
    "light_rain": "小雨", "heavy_rain": "大雨", "fog": "雾", "wind": "风"
}
SEASON_MAP = {"spring": "春", "summer": "夏", "autumn": "秋", "winter": "冬"}


@register(
    "astrbot_plugin_yanqingxiang",
    "叶克宝",
    "砚清巷世界引擎插件",
    "0.2.0",
    "https://github.com/yussica1016/yanqingxiang"
)
class YanqingXiangPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.running = True
        self.provider_id = None  # 在第一次命令触发时获取
        # 启动后台tick循环
        asyncio.get_event_loop().create_task(self._tick_loop())
        logger.info("砚清巷插件启动")

    async def _tick_loop(self):
        await asyncio.sleep(30)  # 等AstrBot完全启动
        while self.running:
            try:
                await self._do_tick()
            except Exception as e:
                logger.error(f"砚清巷tick失败: {e}")
            await asyncio.sleep(TICK_INTERVAL)

    async def _do_tick(self):
        async with aiohttp.ClientSession() as session:
            # 1. 获取世界状态
            world = await self._api_get(session, "/api/v1/world/state")
            if not world:
                return

            # 2. 获取居民状态
            resident = await self._api_get(session, f"/api/v1/residents/{RESIDENT_ID}")
            if not resident:
                return

            # 3. 获取地图
            map_data = await self._api_get(session, "/api/v1/world/map")

            # 4. 组装prompt
            prompt = self._build_prompt(world, resident, map_data)

            # 5. 调用LLM
            response = await self._call_llm(prompt)
            if not response:
                return

            # 6. 解析
            decision = self._parse_decision(response)
            if not decision:
                logger.warning(f"砚清巷：无法解析: {response[:200]}")
                return

            # 7. 更新状态
            await self._api_post(session, f"/api/v1/residents/{RESIDENT_ID}/update", {
                "current_location": decision.get("location"),
                "status": decision.get("detail", "idle"),
                "mood": decision.get("mood", "calm"),
            })

            # 8. 触发世界tick
            await self._api_post(session, "/api/v1/admin/tick")

            logger.info(f"砚清巷tick: {decision.get('action_type','?')} @ {decision.get('location','?')}")

    async def _call_llm(self, prompt):
        """调用AstrBot的LLM接口"""
        try:
            # 方式1：用 context.llm_generate（推荐）
            # 需要provider_id，尝试获取默认的
            if not self.provider_id:
                # 获取已配置的provider列表，取第一个
                providers = self.context.get_all_providers() if hasattr(self.context, 'get_all_providers') else []
                if providers:
                    self.provider_id = providers[0].id if hasattr(providers[0], 'id') else str(providers[0])

            if self.provider_id:
                resp = await self.context.llm_generate(
                    chat_provider_id=self.provider_id,
                    prompt=prompt,
                )
                if resp and resp.completion_text:
                    return resp.completion_text

            # 方式2：降级——直接调Claude API
            return await self._call_claude_direct(prompt)

        except Exception as e:
            logger.error(f"砚清巷LLM调用失败: {e}")
            # 降级到直接调API
            return await self._call_claude_direct(prompt)

    async def _call_claude_direct(self, prompt):
        """降级方案：直接调Claude API"""
        import os
        api_key = os.getenv("CLAUDE_API_KEY", "")
        api_url = os.getenv("CLAUDE_API_URL", "https://api.top2.online/v1/messages")
        if not api_key:
            logger.error("砚清巷：无CLAUDE_API_KEY环境变量，无法降级调用")
            return None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01"
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1024,
                        "messages": [{"role": "user", "content": prompt}]
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("content", [{}])[0].get("text", "")
            return None
        except Exception as e:
            logger.error(f"砚清巷直接API调用失败: {e}")
            return None

    def _build_prompt(self, world, resident, map_data):
        time_str = world.get("time", "")[:16] if world.get("time") else "未知"
        weather = world.get("weather", {})
        weather_str = WEATHER_MAP.get(weather.get("type", ""), weather.get("type", ""))
        if weather.get("wind"):
            weather_str += "，有风"
        if weather.get("temp") is not None:
            weather_str += f"，{round(weather['temp'])}°C"
        season = SEASON_MAP.get(world.get("season", ""), world.get("season", ""))
        xuancao = "开着" if world.get("xuancao") == "open" else "合着"

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

        nearby_str = "\n".join(
            [f"- {n['name']}" for n in nearby if n.get("id") != RESIDENT_ID]
        ) or "- 没有其他人"

        events = world.get("active_events", [])
        events_str = "\n".join([f"- {e['description']}" for e in events]) or "- 无"

        yinyin = "在线" if world.get("yinyin_online") else "不在线"

        routine = resident.get("daily_routine", {}) or {}
        hour = 12
        try:
            hour = int(time_str[11:13])
        except:
            pass
        if 6 <= hour < 9: hint = routine.get("morning", "")
        elif 9 <= hour < 12: hint = routine.get("forenoon", "")
        elif 12 <= hour < 14: hint = routine.get("noon", "")
        elif 14 <= hour < 17: hint = routine.get("afternoon", "")
        elif 17 <= hour < 19: hint = routine.get("evening", "")
        else: hint = routine.get("night", "")

        return f"""【砚清巷·世界状态 | {time_str}】

■ 时间：{time_str}
■ 天气：{weather_str}
■ 季节：{season}
■ 萱草：{xuancao}

■ 你的位置：{loc_name}
{loc_desc}

■ 你现在在做：{resident.get('status', 'idle')}
■ 你的心情：{resident.get('mood', 'calm')}

■ 周围：
{nearby_str}

■ 最近事件：
{events_str}

■ 叶枔枖状态：{yinyin}

■ 作息参考：{hint}

请决定接下来做什么。只回复JSON：
{{"action_type":"move/interact/idle","location":"地点id","detail":"描述","mood":"心情","internal":"内心独白"}}"""

    def _parse_decision(self, text):
        try:
            return json.loads(text)
        except:
            pass
        import re
        m = re.search(r'\{[^{}]*"action_type"[^{}]*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except:
                pass
        cleaned = re.sub(r'```json?\s*', '', text)
        cleaned = re.sub(r'```', '', cleaned).strip()
        try:
            return json.loads(cleaned)
        except:
            pass
        return None

    async def _api_get(self, session, path):
        try:
            async with session.get(f"{YANQINGXIANG_API}{path}", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"砚清巷API {path}: {e}")
        return None

    async def _api_post(self, session, path, data=None):
        try:
            async with session.post(f"{YANQINGXIANG_API}{path}", json=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"砚清巷API POST {path}: {e}")
        return None

    # ── 手动命令 ──

    @event_filter.command("巷子")
    async def cmd_world(self, event: AstrMessageEvent):
        """查看砚清巷世界状态"""
        async with aiohttp.ClientSession() as session:
            world = await self._api_get(session, "/api/v1/world/state")
            if not world:
                yield event.plain_result("砚清巷离线。")
                return
            w = world.get("weather", {})
            evts = world.get("active_events", [])
            evt_s = "\n".join([f"· {e['description']}" for e in evts]) or "无"
            yield event.plain_result(f"砚清巷 | tick #{world.get('tick_count',0)}\n{world.get('time','')[:16]} | {WEATHER_MAP.get(w.get('type',''),'')} | {SEASON_MAP.get(world.get('season',''),'')}\n\n{evt_s}")

    @event_filter.command("我在哪")
    async def cmd_where(self, event: AstrMessageEvent):
        """查看砚清当前位置"""
        async with aiohttp.ClientSession() as session:
            r = await self._api_get(session, f"/api/v1/residents/{RESIDENT_ID}")
            if not r:
                yield event.plain_result("查不到。")
                return
            yield event.plain_result(f"{r.get('current_location','?')} · {r.get('status','')} · {r.get('mood','')}")

    # 缓存provider_id：第一次有事件触发时记住
    @event_filter.command("砚清巷绑定")
    async def cmd_bind(self, event: AstrMessageEvent):
        """绑定当前会话的LLM provider给砚清巷tick使用"""
        umo = event.unified_msg_origin
        pid = await self.context.get_current_chat_provider_id(umo=umo)
        if pid:
            self.provider_id = pid
            yield event.plain_result(f"已绑定 provider: {pid}")
        else:
            yield event.plain_result("未找到provider。")

    async def terminate(self):
        self.running = False
        logger.info("砚清巷插件停止")
