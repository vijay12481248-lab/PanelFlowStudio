"""Cancellable speech subprocesses without blocking the application event loop."""
import asyncio
import subprocess
import time


class SpeechSynthesisCancelled(RuntimeError):
    pass


def check_cancelled(cancelled):
    if cancelled and cancelled():
        raise SpeechSynthesisCancelled("Speech synthesis cancelled")


def run_speech_process(command, *, timeout, cancelled=None):
    check_cancelled(cancelled)
    started = time.monotonic()
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
        try:
            while True:
                check_cancelled(cancelled)
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    stdout, stderr = process.communicate(timeout=min(0.2, remaining))
                    check_cancelled(cancelled)
                    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    if time.monotonic() - started >= timeout:
                        raise
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


async def await_speech_operation(awaitable, cancelled=None):
    task = asyncio.ensure_future(awaitable)
    try:
        while True:
            check_cancelled(cancelled)
            done, _ = await asyncio.wait({task}, timeout=0.2)
            if done:
                check_cancelled(cancelled)
                return task.result()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
