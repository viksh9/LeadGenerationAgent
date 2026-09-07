"""Background scheduler runner.

A single asyncio task that periodically ticks the :class:`SchedulerService`. It
is started ONLY when ``settings.scheduler_active`` is true, so importing the app,
running tests, or CI never spawns it (and thus never makes network calls). Each
tick opens its own DB session and commits per run; a crashing tick is logged and
the loop continues (no silent death).
"""

from __future__ import annotations

import asyncio
import logging

from config import get_settings
from database.repository import create_session_factory
from scheduler.service import SchedulerService

logger = logging.getLogger(__name__)


class SchedulerRunner:
    def __init__(self, *, tick_seconds: int | None = None, session_factory=None):
        settings = get_settings()
        self.tick_seconds = tick_seconds or settings.scheduler_tick_seconds
        self._session_factory = session_factory or create_session_factory()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _seed(self) -> None:
        session = self._session_factory()
        try:
            SchedulerService(session).seed_default_jobs()
            session.commit()
        except Exception:
            session.rollback()
            logger.exception("scheduler seeding failed")
        finally:
            session.close()

    async def _run_loop(self) -> None:
        logger.info("scheduler runner started (tick=%ss)", self.tick_seconds)
        await self._seed()
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self._tick_once)
            except Exception:
                logger.exception("scheduler tick failed (continuing)")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.tick_seconds)
            except asyncio.TimeoutError:
                pass
        logger.info("scheduler runner stopped")

    def _tick_once(self) -> None:
        session = self._session_factory()
        try:
            runs = SchedulerService(session).tick()
            session.commit()
            if runs:
                logger.info("scheduler tick ran %d job(s)", len(runs))
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=self.tick_seconds + 5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None
