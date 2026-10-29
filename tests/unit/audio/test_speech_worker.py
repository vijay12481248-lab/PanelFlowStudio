import asyncio
import subprocess
import sys
import threading
import time

import pytest

from engine.audio.process import SpeechSynthesisCancelled, run_speech_process, await_speech_operation
from engine.pipeline.speech_worker import synthesize_batch_async


@pytest.mark.asyncio
async def test_model_work_does_not_block_event_loop_and_progress_returns_to_loop():
    loop_thread = threading.get_ident()
    worker_threads, progress_threads, ticks = [], [], []
    class Synthesizer:
        def synthesize_batch(self, tasks, progress_cb, cancelled_cb):
            worker_threads.append(threading.get_ident())
            time.sleep(.15)
            progress_cb(.5, "Generating")
            return [{"id": "clip", "success": True}]
    async def heartbeat():
        for _ in range(5):
            await asyncio.sleep(.01)
            ticks.append(1)
    task = asyncio.create_task(synthesize_batch_async(Synthesizer(), [],
        progress=lambda *_: progress_threads.append(threading.get_ident())))
    await heartbeat()
    assert not task.done()
    assert (await task)[0]["success"]
    assert len(ticks) == 5
    assert worker_threads[0] != loop_thread
    assert progress_threads == [loop_thread]


@pytest.mark.asyncio
async def test_cancellation_drains_worker_and_does_not_return_late_result():
    started, finished = threading.Event(), threading.Event()
    class Synthesizer:
        def synthesize_batch(self, tasks, progress_cb, cancelled_cb):
            started.set()
            try:
                while not cancelled_cb():
                    time.sleep(.01)
                raise SpeechSynthesisCancelled()
            finally:
                finished.set()
    task = asyncio.create_task(synthesize_batch_async(Synthesizer(), []))
    while not started.is_set():
        await asyncio.sleep(.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()


def test_real_subprocess_is_reaped_on_cancel(monkeypatch):
    original = subprocess.Popen
    children = []
    def spawn(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(subprocess, "Popen", spawn)
    start = time.monotonic()
    with pytest.raises(SpeechSynthesisCancelled):
        run_speech_process([sys.executable, "-c", "import time; time.sleep(10)"],
                           timeout=20, cancelled=lambda: time.monotonic()-start > .1)
    assert children[0].poll() is not None
    assert time.monotonic()-start < 3


def test_process_timeout_and_output():
    result = run_speech_process([sys.executable, "-c", "print('ready')"], timeout=5)
    assert result.returncode == 0
    assert result.stdout.strip() == "ready"
    with pytest.raises(subprocess.TimeoutExpired):
        run_speech_process([sys.executable, "-c", "import time; time.sleep(10)"], timeout=.1)


@pytest.mark.asyncio
async def test_network_speech_operation_is_cancelled_and_drained():
    stopped = []
    async def network_request():
        try:
            await asyncio.sleep(10)
        finally:
            stopped.append(True)
    start = time.monotonic()
    with pytest.raises(SpeechSynthesisCancelled):
        await await_speech_operation(network_request(), lambda: time.monotonic()-start > .05)
    assert stopped == [True]
