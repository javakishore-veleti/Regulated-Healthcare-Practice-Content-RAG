import asyncio
import functools
from typing import Callable, TypeVar

from opentelemetry import trace

F = TypeVar("F", bound=Callable)


def traced(span_name: str):
    """Wrap a callable in an OTel span using the project's domain-functional naming
    (e.g., 'patterns.list', 'patterns.dao.fetch_all'), not generic technical labels."""
    tracer = trace.get_tracer("ragmgmt-service")

    def decorator(fn: F) -> F:
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                with tracer.start_as_current_span(span_name):
                    return await fn(*args, **kwargs)
            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name):
                return fn(*args, **kwargs)
        return sync_wrapper  # type: ignore[return-value]

    return decorator
