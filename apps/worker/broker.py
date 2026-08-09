from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import Middleware
from zubepredict_core.shared.config import get_settings


class StaleJobRecoveryMiddleware(Middleware):
    """Ask one actor to recover abandoned DB jobs whenever a worker boots."""

    def after_worker_boot(self, broker: RedisBroker, worker: object) -> None:
        del worker
        broker.get_actor("recover_stale_experiments").send()


settings = get_settings()
broker = RedisBroker(url=settings.redis_url)
broker.add_middleware(StaleJobRecoveryMiddleware())
dramatiq.set_broker(broker)
