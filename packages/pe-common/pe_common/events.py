import aio_pika
import json
import uuid
import asyncio
from datetime import datetime
from typing import Callable, Dict
from .logging import get_logger

logger = get_logger(__name__)
EXCHANGE_NAME = "pet-emporio.events"
_subscribers: Dict[str, list] = {}


async def get_connection(url: str) -> aio_pika.Connection:
    return await aio_pika.connect_robust(url)


class EventPublisher:
    _connection: aio_pika.Connection = None
    _channel: aio_pika.Channel = None
    _exchange: aio_pika.Exchange = None
    _url: str = None

    @classmethod
    async def connect(cls, url: str):
        cls._url = url
        cls._connection = await aio_pika.connect_robust(url)
        cls._channel = await cls._connection.channel()
        cls._exchange = await cls._channel.declare_exchange(
            EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
        )

    @classmethod
    async def publish(cls, event_type: str, payload: dict, service: str = "unknown", trace_id: str = None):
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "source_service": service,
            "payload": payload,
            "trace_id": trace_id or str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat()
        }
        await cls._exchange.publish(
            aio_pika.Message(
                body=json.dumps(event).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                content_type="application/json"
            ),
            routing_key=event_type
        )
        logger.info("event_published", event_type=event_type, event_id=event["event_id"])


def event_consumer(event_type: str):
    def decorator(func: Callable):
        if event_type not in _subscribers:
            _subscribers[event_type] = []
        _subscribers[event_type].append(func)
        return func
    return decorator