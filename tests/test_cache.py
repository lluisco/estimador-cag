from app.services.cache import EstimationCache

UNREACHABLE_REDIS_URL = "redis://127.0.0.1:1/0"


def test_make_key_is_deterministic():
    key_a = EstimationCache.make_key(
        system_prompt="prompt", user_message="hola", model="openai/gpt-4o-mini", max_tokens=2000
    )
    key_b = EstimationCache.make_key(
        system_prompt="prompt", user_message="hola", model="openai/gpt-4o-mini", max_tokens=2000
    )
    assert key_a == key_b


def test_make_key_differs_with_input():
    key_a = EstimationCache.make_key(
        system_prompt="prompt", user_message="hola", model="openai/gpt-4o-mini", max_tokens=2000
    )
    key_b = EstimationCache.make_key(
        system_prompt="prompt", user_message="adios", model="openai/gpt-4o-mini", max_tokens=2000
    )
    assert key_a != key_b


def test_get_degrades_gracefully_when_redis_unreachable():
    cache = EstimationCache(redis_url=UNREACHABLE_REDIS_URL, ttl_seconds=60)
    assert cache.get("any-key") is None


def test_set_degrades_gracefully_when_redis_unreachable():
    cache = EstimationCache(redis_url=UNREACHABLE_REDIS_URL, ttl_seconds=60)
    cache.set("any-key", {"text": "sin cache"})
