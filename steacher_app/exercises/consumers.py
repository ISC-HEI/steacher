import asyncio
import json
import time
from typing import Any, Dict, Optional

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from .models import Cohort, Module, Exercise, QuizLog
from .authz import get_user_cohort_role
import redis.asyncio as redis


# -----------------------------
# Redis helper functions
# -----------------------------

_redis_client: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        url = getattr(settings, 'REDIS_URL', 'redis://127.0.0.1:6379/0')
        _redis_client = redis.from_url(url, decode_responses=True)
    return _redis_client


STATE_TTL_SECONDS = 7200
LOCK_TTL_SECONDS = 60
PRESENCE_STALE_AFTER_SECONDS = 30


def _state_key(cohort_id: Any, module_id: Any) -> str:
    return f"quiz:state:{cohort_id}:{module_id}"


def _presence_key(cohort_id: Any) -> str:
    # Using a sorted set with timestamps as scores to emulate per-member TTL
    return f"quiz:presence:{cohort_id}"


def _lock_key(cohort_id: Any, module_id: Any) -> str:
    return f"quiz:lock:{cohort_id}:{module_id}"


async def get_state(cohort_id: Any, module_id: Any) -> Dict[str, Any]:
    r = _get_redis()
    key = _state_key(cohort_id, module_id)
    data = await r.hgetall(key)
    return data or {}


async def set_state(cohort_id: Any, module_id: Any, **fields: Any) -> None:
    r = _get_redis()
    key = _state_key(cohort_id, module_id)
    # Normalize None by deleting fields instead of setting literal 'None'
    delete_fields = [k for k, v in fields.items() if v is None]
    if delete_fields:
        await r.hdel(key, *delete_fields)
    to_set = {k: str(v) for k, v in fields.items() if v is not None}
    if to_set:
        await r.hset(key, mapping=to_set)
    await r.expire(key, STATE_TTL_SECONDS)


async def set_countdown(cohort_id: Any, module_id: Any, duration_sec: int) -> Dict[str, Any]:
    now = int(time.time())
    end_ts = now + max(5, int(duration_sec))
    await set_state(cohort_id, module_id,
                    countdown_duration=duration_sec,
                    countdown_end_time=end_ts)
    return {"countdown_duration": duration_sec, "countdown_end_time": end_ts}


async def clear_countdown(cohort_id: Any, module_id: Any) -> None:
    await set_state(cohort_id, module_id, countdown_duration=None, countdown_end_time=None)


async def presence_heartbeat(cohort_id: Any, user_id: Any) -> None:
    r = _get_redis()
    key = _presence_key(cohort_id)
    now = int(time.time())
    # Store heartbeat in ZSET with timestamp score
    await r.zadd(key, {str(user_id): now})
    # Keep key alive while quiz is active
    await r.expire(key, STATE_TTL_SECONDS)


async def presence_count(cohort_id: Any) -> int:
    r = _get_redis()
    key = _presence_key(cohort_id)
    now = int(time.time())
    cutoff = now - PRESENCE_STALE_AFTER_SECONDS
    # Remove stale entries and return current count
    await r.zremrangebyscore(key, 0, cutoff)
    return int(await r.zcard(key))


async def presence_remove(cohort_id: Any, user_id: Any) -> None:
    r = _get_redis()
    key = _presence_key(cohort_id)
    try:
        await r.zrem(key, str(user_id))
    except Exception:
        # Best-effort removal
        pass


async def acquire_lock(cohort_id: Any, module_id: Any, teacher_id: Any) -> bool:
    r = _get_redis()
    key = _lock_key(cohort_id, module_id)
    # SET with NX and EX ensures exclusive lock with TTL
    return bool(await r.set(key, str(teacher_id), ex=LOCK_TTL_SECONDS, nx=True))


async def has_lock(cohort_id: Any, module_id: Any, teacher_id: Any) -> bool:
    r = _get_redis()
    key = _lock_key(cohort_id, module_id)
    val = await r.get(key)
    return val == str(teacher_id)


async def refresh_lock(cohort_id: Any, module_id: Any, teacher_id: Any) -> bool:
    r = _get_redis()
    key = _lock_key(cohort_id, module_id)
    # Refresh only if the same owner
    if await has_lock(cohort_id, module_id, teacher_id):
        await r.expire(key, LOCK_TTL_SECONDS)
        return True
    return False


async def release_lock_if_owner(cohort_id: Any, module_id: Any, teacher_id: Any) -> bool:
    r = _get_redis()
    key = _lock_key(cohort_id, module_id)
    # Lua to check-and-delete atomically
    script = """
    if redis.call('GET', KEYS[1]) == ARGV[1] then
        return redis.call('DEL', KEYS[1])
    else
        return 0
    end
    """
    res = await r.eval(script, 1, key, str(teacher_id))
    return bool(res)


# Atomic state transitions
async def start_gathering(cohort_id: Any, module_id: Any, teacher_id: Any) -> None:
    await set_state(cohort_id, module_id,
                    state='gathering',
                    current_exercise_id=None,
                    teacher_id=teacher_id)
    await clear_countdown(cohort_id, module_id)


async def start_quiz(cohort_id: Any, module_id: Any, first_exercise_id: Any) -> None:
    await set_state(cohort_id, module_id,
                    state='display_question',
                    current_exercise_id=first_exercise_id)
    await clear_countdown(cohort_id, module_id)


async def go_to_exercise(cohort_id: Any, module_id: Any, exercise_id: Any) -> None:
    await set_state(cohort_id, module_id,
                    state='display_question',
                    current_exercise_id=exercise_id)
    await clear_countdown(cohort_id, module_id)


async def finish_question_to_results(cohort_id: Any, module_id: Any) -> None:
    await set_state(cohort_id, module_id, state='results_for_current_question')
    await clear_countdown(cohort_id, module_id)


async def end_quiz(cohort_id: Any, module_id: Any) -> None:
    await set_state(cohort_id, module_id, state='completed')
    await clear_countdown(cohort_id, module_id)


async def delete_quiz_state(cohort_id: Any, module_id: Any) -> None:
    """Delete all quiz state from Redis for a cohort/module."""
    r = _get_redis()
    await r.delete(_state_key(cohort_id, module_id))
    await r.delete(_lock_key(cohort_id, module_id))
    # Note: presence is cohort-wide, not module-specific


class QuizConsumer(AsyncWebsocketConsumer):
    """
    Single consumer for teacher and students. 
    """

    async def connect(self):
        # Extract URL params
        kwargs = (self.scope.get('url_route') or {}).get('kwargs') or {}
        self.cohort_id = int(kwargs.get('cohort_id'))
        self.module_id = int(kwargs.get('module_id'))
        self.group_name = f"quiz_{self.cohort_id}_{self.module_id}"

        # Resolve objects (DB hits are okay once per connection)
        try:
            self.cohort: Cohort = await Cohort.objects.select_related('course').aget(pk=self.cohort_id)
            self.module: Module = await Module.objects.select_related('course').aget(pk=self.module_id)
        except Exception:
            # If objects are missing, reject connection
            await self.close(code=4404)
            return

        # Determine role once per connection
        user = self.scope.get('user')
        self.user_id = getattr(user, 'id', None)
        try:
            role = await self._get_role_async(user)
        except Exception:
            role = None
        self.is_teacher = role in {'owner', 'teacher', 'viewer'}

        # Join group and accept
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Initial presence update for students only
        if not self.is_teacher and self.user_id is not None:
            await presence_heartbeat(self.cohort_id, self.user_id)
            # Broadcast updated presence to all listeners (teacher + students)
            await self._broadcast_state()

        # Send current state to client for hydration
        await self._send_state_update()

    async def disconnect(self, close_code):
        try:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
        except Exception:
            # Best-effort cleanup
            pass
        # If a student leaves, remove their presence immediately and broadcast updated count
        try:
            if not getattr(self, 'is_teacher', False) and getattr(self, 'user_id', None) is not None:
                await presence_remove(self.cohort_id, self.user_id)
                await self._broadcast_state()
        except Exception:
            pass

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            msg = json.loads(text_data)
        except Exception:
            return

        action = (msg.get('action') or '').strip()
        payload = msg.get('payload') or {}

        # Student heartbeats
        if action == 'presence_heartbeat':
            if self.user_id is not None:
                await presence_heartbeat(self.cohort_id, self.user_id)
            # Broadcast updated presence (and state for safety) to the group
            await self._broadcast_state()
            return

        # Non-teachers cannot perform control actions
        if not self.is_teacher:
            return

        # Lock acquisition + heartbeat
        if action == 'acquire_lock':
            ok = await acquire_lock(self.cohort_id, self.module_id, self.user_id)
            # Reply with lock status
            await self.send(text_data=json.dumps({'type': 'lock', 'ok': ok}))
            return

        if action == 'lock_heartbeat':
            ok = await refresh_lock(self.cohort_id, self.module_id, self.user_id)
            await self.send(text_data=json.dumps({'type': 'lock_heartbeat', 'ok': ok}))
            return

        # All remaining teacher actions require holding the lock
        if not await has_lock(self.cohort_id, self.module_id, self.user_id):
            return

        if action == 'start_gathering':
            await start_gathering(self.cohort_id, self.module_id, self.user_id)
            await self._broadcast_state()
            return

        if action == 'start_quiz':
            # Teacher provides the first exercise id
            ex_id = payload.get('exercise_id')
            if ex_id is None:
                return
            await start_quiz(self.cohort_id, self.module_id, int(ex_id))
            await self._broadcast_state()
            return

        if action == 'start_countdown':
            duration = int(payload.get('duration') or 5)
            info = await set_countdown(self.cohort_id, self.module_id, duration)
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'countdown_start',
                    'event': 'countdown_start',
                    'cohort_id': self.cohort_id,
                    'module_id': self.module_id,
                    **info,
                },
            )
            # Spawn async task to auto-transition to results when countdown finishes
            asyncio.create_task(self._auto_finish_countdown(duration))
            return

        if action == 'next_question':
            # Teacher provides the target exercise id (next or jump)
            ex_id = payload.get('exercise_id')
            if ex_id is None:
                return
            await go_to_exercise(self.cohort_id, self.module_id, int(ex_id))
            await self._broadcast_state()
            return

        if action == 'end_quiz':
            # Get presence count before ending (for QuizLog)
            try:
                student_count = await presence_count(self.cohort_id)
            except Exception:
                student_count = 0
            
            await end_quiz(self.cohort_id, self.module_id)
            
            # Persist quiz completion to database
            try:
                await database_sync_to_async(QuizLog.objects.create)(
                    cohort_id=self.cohort_id,
                    module_id=self.module_id,
                    teacher_id=self.user_id,
                    student_count=student_count
                )
            except Exception as e:
                # Log but don't fail (quiz state already set to completed)
                print(f"[QuizConsumer] Failed to create QuizLog: {e}")
            
            await self._broadcast_state()
            return

    # Example handler to verify group routing in later steps
    async def quiz_state_update(self, event):
        await self.send(text_data=json.dumps(event))

    async def countdown_start(self, event):
        await self.send(text_data=json.dumps(event))


    # -------------
    # Helpers
    # -------------

    async def _get_role_async(self, user) -> Optional[str]:
        try:
            return await database_sync_to_async(get_user_cohort_role)(user, self.cohort)
        except Exception:
            return None

    async def _auto_finish_countdown(self, duration: int) -> None:
        """
        Wait for countdown duration, then automatically transition to results state.
        Server is the single source of truth for countdown expiry.
        """
        await asyncio.sleep(duration)
        await finish_question_to_results(self.cohort_id, self.module_id)
        await self._broadcast_state()


    async def _send_state_update(self, *, include_presence_only: bool = False) -> None:
        state = await get_state(self.cohort_id, self.module_id)
        try:
            present = await presence_count(self.cohort_id)
        except Exception:
            present = 0
        event = {
            'type': 'quiz_state_update',
            'cohort_id': self.cohort_id,
            'module_id': self.module_id,
            'state': state,
            'presence': {'count': present},
        }
        if include_presence_only:
            event['only'] = 'presence'
        await self.send(text_data=json.dumps(event))

    async def _broadcast_state(self) -> None:
        state = await get_state(self.cohort_id, self.module_id)
        present = await presence_count(self.cohort_id)
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'quiz_state_update',
                'cohort_id': self.cohort_id,
                'module_id': self.module_id,
                'state': state,
                'presence': {'count': present},
            },
        )


