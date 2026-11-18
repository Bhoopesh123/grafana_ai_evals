import logging
import os

import openlit

from .config import settings


logger = logging.getLogger(__name__)
_initialized = False


def initialize_openlit() -> None:
    """Add OpenLIT auto-instrumentation alongside the custom OTel spans."""
    global _initialized
    if _initialized or os.getenv("OPENLIT_ENABLED", "true").lower() != "true":
        return

    openlit.init(
        service_name=os.getenv("OTEL_SERVICE_NAME", "streamlit-genai-app"),
        environment="local",
        otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317"),
        capture_message_content=settings.capture_content,
        collect_gpu_stats=False,
        collect_system_metrics=False,
        capture_db_parameters=False,
        disabled_instrumentors=["httpx", "requests", "tornado", "urllib", "urllib3"],
        disable_events=True,
    )
    _initialized = True
    logger.info("OpenLIT auto-instrumentation enabled")
