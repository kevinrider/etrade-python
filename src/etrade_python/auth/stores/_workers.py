"""Wait for keyring and lock workers before relinquishing transaction ownership."""

import asyncio
import contextvars
from collections.abc import Callable
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")


async def run_worker(function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """Defer cancellation until a worker finishes, including repeated cancellation.

    A worker thread cannot be stopped by cancelling its awaiter. Releasing a
    namespace lock first would allow its late write to race with the next owner.
    """
    context = contextvars.copy_context()
    # Use an executor Future, not a Task: asyncio.run() cancels all Tasks during
    # shutdown, including a shielded to_thread Task. This Future stays alive until
    # the actual thread finishes, so the transaction cannot unlock prematurely.
    worker = asyncio.get_running_loop().run_in_executor(
        None, lambda: context.run(function, *args, **kwargs)
    )
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancelled = True
            if not worker.done():
                continue
            # Retrieve worker exceptions even when cancellation wins.
            if not worker.cancelled():
                worker.exception()
            raise
        except Exception:
            if cancelled:
                raise asyncio.CancelledError from None
            raise
        else:
            if cancelled:
                raise asyncio.CancelledError
            return result
