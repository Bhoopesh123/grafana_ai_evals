import json
import logging
import math
import os
import random
import time

from opentelemetry import metrics

from .telemetry import meter


VECTOR_ATTRIBUTES = {"db.system.name": "in_memory", "db.namespace": "demo_documents"}
MCP_ATTRIBUTES = {"mcp.client.type": "demo-client", "mcp.transport.type": "stdio"}

db_duration = meter.create_histogram("db.client.operation.duration", unit="s")
db_requests = meter.create_counter("db.requests", unit="{request}")

mcp_duration = meter.create_histogram("mcp.client.operation.duration", unit="s")
mcp_requests = meter.create_counter("mcp.requests", unit="{request}")
mcp_errors = meter.create_counter("mcp.errors", unit="{error}")
mcp_tool_calls = meter.create_counter("mcp.tool.calls", unit="{call}")
mcp_request_size = meter.create_histogram("mcp.request.size", unit="By")
mcp_response_size = meter.create_histogram("mcp.response.size", unit="By")

gpu_metrics = {
    name: meter.create_gauge(name)
    for name in (
        "gpu.power.draw",
        "gpu.power.limit",
        "gpu.fan.speed",
        "gpu.memory.used",
        "gpu.memory.free",
        "gpu.memory.total",
        "gpu.memory.available",
        "gpu.temperature",
        "gpu.utilization",
        "gpu.dec.utilization",
        "gpu.enc.utilization",
    )
}

DOCUMENTS = {
    "otel": (0.92, 0.15, 0.08, 0.35),
    "grafana": (0.78, 0.55, 0.11, 0.42),
    "openlit": (0.88, 0.34, 0.25, 0.63),
    "mcp": (0.21, 0.87, 0.54, 0.31),
}


def vector_search(iteration: int) -> None:
    started = time.perf_counter()
    query = tuple(random.random() for _ in range(4))
    ranked = sorted(
        DOCUMENTS,
        key=lambda name: sum((left - right) ** 2 for left, right in zip(query, DOCUMENTS[name])),
    )
    _ = ranked[:2]
    attrs = {**VECTOR_ATTRIBUTES, "db.operation.name": "query" if iteration % 4 else "upsert"}
    db_requests.add(1, attrs)
    db_duration.record(time.perf_counter() - started, attrs)


def call_mcp_tool(iteration: int) -> None:
    tool_name = ("add", "echo", "document_lookup")[iteration % 3]
    request = {"tool": tool_name, "arguments": {"value": iteration, "text": "OpenLIT demo"}}
    encoded_request = json.dumps(request).encode()
    attrs = {**MCP_ATTRIBUTES, "mcp.tool.name": tool_name, "mcp.method": "tools/call"}
    started = time.perf_counter()
    mcp_requests.add(1, attrs)
    mcp_tool_calls.add(1, attrs)
    mcp_request_size.record(len(encoded_request), attrs)
    try:
        if iteration % 25 == 0:
            raise ValueError("intentional demo error")
        if tool_name == "add":
            result = {"result": iteration + 2}
        elif tool_name == "echo":
            result = {"result": request["arguments"]["text"]}
        else:
            result = {"result": list(DOCUMENTS)[:2]}
        mcp_response_size.record(len(json.dumps(result).encode()), attrs)
    except ValueError:
        mcp_errors.add(1, attrs)
    finally:
        mcp_duration.record(time.perf_counter() - started, attrs)


def record_simulated_gpu(iteration: int) -> None:
    wave = (math.sin(iteration / 8) + 1) / 2
    total = 24 * 1024**3
    used = int(total * (0.28 + 0.42 * wave))
    attrs = {"gpu.index": "0", "gpu.name": "OpenLIT Demo GPU", "gpu.mode": "simulated"}
    values = {
        "gpu.power.draw": 80 + 170 * wave,
        "gpu.power.limit": 300,
        "gpu.fan.speed": 25 + 55 * wave,
        "gpu.memory.used": used,
        "gpu.memory.free": total - used,
        "gpu.memory.total": total,
        "gpu.memory.available": total,
        "gpu.temperature": 42 + 31 * wave,
        "gpu.utilization": 18 + 78 * wave,
        "gpu.dec.utilization": 4 + 18 * wave,
        "gpu.enc.utilization": 3 + 15 * wave,
    }
    for name, value in values.items():
        gpu_metrics[name].set(value, attrs)


def main() -> None:
    gpu_simulation = os.getenv("DEMO_GPU_SIMULATION", "true").lower() == "true"
    interval = max(float(os.getenv("DEMO_WORKLOAD_INTERVAL_SECONDS", "1")), 0.1)
    logging.info(
        "OpenLIT dashboard demo workload ready gpu_simulation=%s interval_seconds=%s",
        gpu_simulation,
        interval,
    )
    iteration = 1
    while True:
        vector_search(iteration)
        call_mcp_tool(iteration)
        if gpu_simulation:
            record_simulated_gpu(iteration)
        iteration += 1
        time.sleep(interval)


if __name__ == "__main__":
    main()
