"""In-process wake-ups for the worker and SSE tails. The database stays the source of truth.

ponytail: in-process only (one Uvicorn worker by design); use PostgreSQL LISTEN/NOTIFY if the
app ever runs more than one process.
"""

import asyncio
from uuid import UUID


class Notifier:
    def __init__(self) -> None:
        self._work = asyncio.Event()
        self._cond = asyncio.Condition()
        self._counter: dict[str, int] = {}  # keyed by str(run_id): UUID or str callers

    def wake_worker(self) -> None:
        self._work.set()

    async def wait_for_work(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._work.wait(), seconds)
        except TimeoutError:
            pass
        finally:
            self._work.clear()

    def seen(self, run_id: UUID | str) -> int:
        """Capture before reading events; `wait_change` then cannot miss a later commit."""
        return self._counter.get(str(run_id), 0)

    async def notify_run(self, run_id: UUID | str, final: bool = False) -> None:
        key = str(run_id)
        self._counter[key] = self.seen(run_id) + 1
        async with self._cond:
            self._cond.notify_all()
        if final:  # keep the entry briefly for late tails, then drop it (bounded memory)
            asyncio.get_running_loop().call_later(60, self._counter.pop, key, None)

    async def wait_change(self, run_id: UUID | str, seen: int, seconds: float) -> bool:
        async with self._cond:
            try:
                await asyncio.wait_for(
                    self._cond.wait_for(lambda: self.seen(run_id) != seen), seconds
                )
                return True
            except TimeoutError:
                return False
