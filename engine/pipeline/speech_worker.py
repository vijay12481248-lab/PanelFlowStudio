"""Keep model work off the API event loop and drain it before releasing a stage."""
import asyncio
import threading

from engine.audio.process import SpeechSynthesisCancelled


async def synthesize_batch_async(synthesizer, tasks, progress=None, cancelled=lambda: False):
    stop = threading.Event()
    loop = asyncio.get_running_loop()

    def is_cancelled():
        return stop.is_set() or cancelled()

    def deliver_progress(*args):
        if progress and not is_cancelled():
            progress(*args)

    def on_progress(*args):
        loop.call_soon_threadsafe(deliver_progress, *args)

    worker = asyncio.create_task(asyncio.to_thread(
        synthesizer.synthesize_batch, tasks, progress_cb=on_progress, cancelled_cb=is_cancelled))
    try:
        result = await asyncio.shield(worker)
        if is_cancelled():
            raise asyncio.CancelledError()
        return result
    except SpeechSynthesisCancelled as error:
        raise asyncio.CancelledError() from error
    except asyncio.CancelledError:
        stop.set()
        # The native worker polls cancellation. Do not leave GPU work running while
        # a retry starts another model session, or allow it to publish late results.
        await asyncio.gather(worker, return_exceptions=True)
        raise
