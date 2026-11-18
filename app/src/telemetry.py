import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_telemetry():
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    logs_endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT",
        endpoint.removesuffix(":4317") + ":4318/v1/logs" if endpoint.endswith(":4317") else endpoint,
    )
    service = os.getenv("OTEL_SERVICE_NAME", "streamlit-genai-app")
    resource = Resource.create({
        "service.name": service,
        "service.version": "0.1.0",
        "deployment.environment": "local",
        "eval.framework": "grafana-ai-evals",
        # OpenLIT reuses this provider; its official Grafana dashboards select this resource label.
        "telemetry.sdk.name": "openlit",
    })

    trace_provider = TracerProvider(resource=resource)
    trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(trace_provider)

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True), export_interval_millis=5000
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=logs_endpoint))
    )
    logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))
    return trace.get_tracer(service), metrics.get_meter(service)


tracer, meter = configure_telemetry()
requests_counter = meter.create_counter("genai.requests", unit="{request}")
request_duration = meter.create_histogram("genai.request.duration", unit="s")
eval_counter = meter.create_counter("genai.eval.runs", unit="{evaluation}")
eval_score = meter.create_histogram("genai.eval.score", unit="1", explicit_bucket_boundaries_advisory=[0, .25, .5, .7, .8, .9, 1])
eval_duration = meter.create_histogram("genai.eval.duration", unit="s")
