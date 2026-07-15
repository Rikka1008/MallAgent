import json
import logging

logger = logging.getLogger("after_sales.audit")


def record_event(event: str, payload: dict) -> None:
    """Emit one structured audit event without changing the request flow."""
    logger.info("%s %s", event, json.dumps(payload, ensure_ascii=False, default=str))
