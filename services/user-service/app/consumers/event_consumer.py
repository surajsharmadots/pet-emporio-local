import json
import asyncio
import aio_pika

from pe_common.logging import get_logger

from ..config import settings
from ..database import AsyncSessionLocal
from ..domains.users.service import UserService

logger = get_logger(__name__)

EXCHANGE_NAME = "pet-emporio.events"
QUEUE_NAME = "user-service.user.login"


async def _handle_user_login(payload: dict):
    mobile = payload.get("mobile")
    if not mobile:
        logger.warning("user_login_event_missing_mobile", payload=payload)
        return
    async with AsyncSessionLocal() as db:
        svc = UserService(db)
        user = await svc.get_or_create_by_mobile(mobile)
        await db.commit()
        logger.info("user_login_processed", user_id=str(user.id))


async def start_consumer():
    try:
        connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)

        exchange = await channel.declare_exchange(
            EXCHANGE_NAME, aio_pika.ExchangeType.TOPIC, durable=True
        )
        queue = await channel.declare_queue(QUEUE_NAME, durable=True)
        await queue.bind(exchange, routing_key="user.login")

        async def on_message(message: aio_pika.IncomingMessage):
            async with message.process(requeue=False):
                try:
                    event = json.loads(message.body.decode())
                    await _handle_user_login(event.get("payload", {}))
                except Exception as e:
                    logger.error("user_login_consumer_error", error=str(e))

        await queue.consume(on_message)
        logger.info("event_consumer_started", queue=QUEUE_NAME)
        # Keep consumer running in background — caller holds reference to connection
        return connection
    except Exception as e:
        logger.warning("event_consumer_failed_to_start", error=str(e))
        return None