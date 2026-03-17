"""
OpenTelemetry distributed tracing for multi-agent pipeline.
Per-agent execution spans, LLM latency tracking, and Jaeger-compatible trace export.
"""

from contextlib import contextmanager
from typing import Optional

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource

    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False


class TracingManager:
    """
    Manages OpenTelemetry tracing configuration.
    Supports console (dev) and OTLP/gRPC (Jaeger) exporters.
    """

    def __init__(
        self,
        enabled: bool = True,
        exporter: str = "console",  # "console" | "otlp"
        endpoint: str = "http://localhost:4317",
        service_name: str = "wandai-backend",
    ):
        self.enabled = enabled and HAS_OTEL
        self._provider: Optional[TracerProvider] = None

        if not self.enabled:
            return

        resource = Resource.create({"service.name": service_name})
        self._provider = TracerProvider(resource=resource)

        if exporter == "otlp":
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
                self._provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            except ImportError:
                # Fall back to console if OTLP package not installed
                self._provider.add_span_processor(
                    BatchSpanProcessor(ConsoleSpanExporter())
                )
        else:
            self._provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )

        trace.set_tracer_provider(self._provider)

    def get_tracer(self, name: str = "wandai"):
        """Get a tracer instance."""
        if not self.enabled:
            return _NoOpTracer()
        return trace.get_tracer(name)

    def shutdown(self):
        """Shutdown the tracer provider."""
        if self._provider:
            self._provider.shutdown()


# Module-level singleton
_manager: Optional[TracingManager] = None


def init_tracing(
    enabled: bool = True,
    exporter: str = "console",
    endpoint: str = "http://localhost:4317",
) -> TracingManager:
    """Initialize the global tracing manager."""
    global _manager
    _manager = TracingManager(enabled=enabled, exporter=exporter, endpoint=endpoint)
    return _manager


def get_tracer(name: str = "wandai"):
    """Get a tracer from the global manager."""
    if _manager is None:
        return _NoOpTracer()
    return _manager.get_tracer(name)


class _NoOpSpan:
    """No-op span for when tracing is disabled."""

    def set_attribute(self, key, value):
        pass

    def set_status(self, status):
        pass

    def record_exception(self, exc):
        pass

    def end(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _NoOpTracer:
    """No-op tracer for when OpenTelemetry is not installed or disabled."""

    def start_span(self, name, **kwargs):
        return _NoOpSpan()

    @contextmanager
    def start_as_current_span(self, name, **kwargs):
        yield _NoOpSpan()
