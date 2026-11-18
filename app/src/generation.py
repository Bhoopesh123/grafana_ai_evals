import json
import random
import time
import uuid

import redis
from openai import OpenAI
from opentelemetry.trace import Status, StatusCode

from .config import settings
from .openlit_setup import initialize_openlit
from .rag import retrieve
from .telemetry import request_duration, requests_counter, tracer


initialize_openlit()


def answer(question: str):
    settings.require_openai_key()
    request_id = str(uuid.uuid4())
    started = time.perf_counter()
    client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    with tracer.start_as_current_span("chat.request") as root:
        root.set_attribute("app.request.id", request_id)
        with tracer.start_as_current_span("rag.retrieve") as span:
            contexts = retrieve(question)
            span.set_attribute("rag.document.count", len(contexts))
            span.set_attribute("rag.document.ids", [c["id"] for c in contexts])
        context_text = "\n\n".join(f"[{c['id']}] {c['text']}" for c in contexts) or "No relevant local context was retrieved."
        messages = [
            {"role": "system", "content": "Answer every user question helpfully. Use supplied context when it is relevant and cite its document IDs in square brackets. If the local context is absent or insufficient, answer from your general knowledge without inventing document citations. Clearly say when you are uncertain."},
            {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion: {question}"},
        ]
        try:
            with tracer.start_as_current_span("gen_ai.chat") as span:
                span.set_attribute("gen_ai.system", "openai")
                span.set_attribute("gen_ai.request.model", settings.generation_model)
                stream = client.chat.completions.create(model=settings.generation_model, messages=messages, stream=True)
                chunks = []
                for event in stream:
                    token = event.choices[0].delta.content or ""
                    if token:
                        chunks.append(token)
                        yield {"type": "token", "value": token}
                response = "".join(chunks)
                span.set_attribute("gen_ai.response.length", len(response))
                trace_id = format(root.get_span_context().trace_id, "032x")
                span_id = format(root.get_span_context().span_id, "016x")
            duration = time.perf_counter() - started
            requests_counter.add(1, {"model": settings.generation_model, "status": "ok"})
            request_duration.record(duration, {"model": settings.generation_model})
            if random.random() <= settings.eval_sample_rate:
                job = {
                    "request_id": request_id, "origin_trace_id": trace_id, "origin_span_id": span_id,
                    "question": question,
                    "response": response, "contexts": contexts, "generation_model": settings.generation_model,
                    "rubric_version": settings.rubric_version,
                }
                redis.from_url(settings.redis_url, decode_responses=True).rpush("eval:all", json.dumps(job))
            yield {"type": "done", "request_id": request_id, "trace_id": trace_id}
        except Exception as exc:
            root.record_exception(exc)
            root.set_status(Status(StatusCode.ERROR, str(exc)))
            requests_counter.add(1, {"model": settings.generation_model, "status": "error"})
            raise
