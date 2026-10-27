import json

import redis

from shared.config import QUEUE_ORGANIZE, QUEUE_PDF, REDIS_URL

_client = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    return _client


def push(queue: str, payload: dict) -> None:
    get_client().lpush(queue, json.dumps(payload))


def pop(queue: str, timeout: int = 5) -> dict | None:
    item = get_client().brpop(queue, timeout=timeout)
    if not item:
        return None
    _, raw = item
    return json.loads(raw)


def queue_pdf(document_id: int) -> None:
    push(QUEUE_PDF, {"document_id": document_id})


def queue_organize(document_id: int) -> None:
    push(QUEUE_ORGANIZE, {"document_id": document_id})
