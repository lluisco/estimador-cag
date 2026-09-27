import hashlib
import json
import logging

import redis

log = logging.getLogger(__name__)


class EstimationCache:
    def __init__(self, redis_url: str, ttl_seconds: int):
        self.ttl_seconds = ttl_seconds
        self._client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )

    @staticmethod
    def make_key(*, system_prompt: str, user_message: str, model: str, max_tokens: int) -> str:
        raw = json.dumps(
            {
                "system_prompt": system_prompt,
                "user_message": user_message,
                "model": model,
                "max_tokens": max_tokens,
            },
            sort_keys=True,
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"estimation:{digest}"

    def get(self, key: str) -> dict | None:
        try:
            raw = self._client.get(key)
        except redis.RedisError:
            log.warning("cache_get_failed key=%s", key)
            return None
        return json.loads(raw) if raw else None

    def set(self, key: str, value: dict) -> None:
        try:
            self._client.set(key, json.dumps(value), ex=self.ttl_seconds)
        except redis.RedisError:
            log.warning("cache_set_failed key=%s", key)