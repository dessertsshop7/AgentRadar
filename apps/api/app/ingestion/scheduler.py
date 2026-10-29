import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.ingestion.sync import SyncService

logger = logging.getLogger("agentradar")


class SyncScheduler:
    def __init__(self, engine, settings):
        self.service = SyncService(engine, settings)
        self.scheduler = AsyncIOScheduler(timezone="UTC")
        self.tasks = set()
        self.startup_task = None

    async def poll(self):
        task = asyncio.current_task()
        self.tasks.add(task)
        try:
            await self.service.tick()
        except asyncio.CancelledError:
            # SyncService 先记录中断并释放数据库锁；不让调度器输出内部堆栈。
            return
        except Exception as exc:
            logger.error("sync_scheduler_error", extra={"error_type": type(exc).__name__})
        finally:
            self.tasks.discard(task)

    def start(self):
        self.scheduler.add_job(
            self.poll, "interval", seconds=60, id="source-sync", coalesce=True, max_instances=1
        )
        self.scheduler.start()
        self.startup_task = asyncio.create_task(self.poll())

    async def stop(self):
        self.scheduler.shutdown(wait=False)
        tasks = self.tasks | ({self.startup_task} if self.startup_task else set())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
