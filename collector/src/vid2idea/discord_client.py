import asyncio
import discord
from .capture import capture_message
from .worker import event


class IdeaClient(discord.Client):
    def __init__(self, settings, outbox, cloud=None, worker=None, history_only=False):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents, max_messages=None)
        self.settings, self.outbox, self.cloud, self.worker = settings,outbox,cloud,worker
        self.history_only = history_only
        self.catchup_lock = asyncio.Lock()
        self.worker_task = None
        self.heartbeat_task = None
        self.history_task = None
        self.history_error = None

    async def setup_hook(self):
        if not self.history_only:
            self.history_task = asyncio.create_task(self.history_loop())
        if self.worker:
            self.worker_task = asyncio.create_task(self.work_loop())
            self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())

    async def on_message(self, message):
        captures = capture_message(message,self.settings)
        if captures:
            # Gateway events must NOT move the history cursor ahead of unseen messages.
            self.outbox.enqueue(captures,self.settings.discord_channel_id,self.outbox.cursor(self.settings.discord_channel_id) or '0')
            event('links_captured','gateway',job_id=str(message.id),count=len(captures))

    async def on_ready(self):
        if not self.history_only:
            return
        try:
            await self.catch_up()
            self.history_error = None
        except Exception:
            self.history_error = 'discord_history_unavailable'
            event('history_unavailable','import-history' if self.history_only else 'run',job_id='history',error_code='discord_history_unavailable')
        await self.close()

    async def history_loop(self):
        await self.wait_until_ready()
        delay = 5
        while not self.is_closed():
            try:
                await self.catch_up()
                self.history_error = None
                delay = 5
                await asyncio.sleep(300)
            except Exception:
                self.history_error = 'discord_history_unavailable'
                event('history_unavailable','run',job_id='history',error_code=self.history_error)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 300)

    async def catch_up(self):
        async with self.catchup_lock:
            channel = await self.fetch_channel(int(self.settings.discord_channel_id))
            cursor = self.outbox.cursor(self.settings.discord_channel_id)
            after = discord.Object(id=int(cursor)) if cursor else None
            count = 0
            async for message in channel.history(limit=None,after=after,oldest_first=True):
                captures = capture_message(message,self.settings)
                self.outbox.enqueue(captures,self.settings.discord_channel_id,str(message.id))
                count += len(captures)
            event('history_imported','import-history' if self.history_only else 'run',job_id='history',count=count)

    async def work_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                requests = await asyncio.to_thread(self.cloud.list_retry_requests)
                for request in requests:
                    self.outbox.enqueue_retry(request)
            except Exception:
                event('refresh_poll_unavailable','run',job_id='sync',error_code='cloud_unavailable')
            try:
                processing = asyncio.create_task(asyncio.to_thread(self.worker.run_once))
                try:
                    await asyncio.shield(processing)
                except asyncio.CancelledError:
                    # The model/media process owns a bounded deadline. Finish its
                    # durable publication before closing the outbox connection.
                    await processing
                    raise
            except Exception:
                event('sync_unavailable','run',job_id='sync',error_code='cloud_unavailable')
            await asyncio.sleep(5 if self.outbox.pending_count() else 30)

    async def heartbeat_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await asyncio.to_thread(self.cloud.record_status,self.outbox.pending_count(),self.history_error or self.worker.last_error_code)
            except Exception:
                pass
            await asyncio.sleep(30)

    async def close(self):
        if self.history_task:
            self.history_task.cancel()
            try:
                await self.history_task
            except asyncio.CancelledError:
                pass
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        await super().close()
