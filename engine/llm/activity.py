"""Request-scoped model telemetry. Never publish prompt or generated content."""
from contextvars import ContextVar

activity_sink = ContextVar("model_activity_sink", default=None)
generation_cancelled = ContextVar("model_generation_cancelled", default=None)


def publish_activity(activity):
    sink = activity_sink.get()
    if sink:
        sink(activity)
