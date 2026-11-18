# Open-source Grafana GenAI evaluation framework

## 1. Goal and scope

Build a local, reproducible reference system in which a Streamlit RAG/chat application generates OpenAI traffic, an asynchronous LLM-as-a-judge service evaluates sampled answers, and all operational and evaluation telemetry is sent by OpenTelemetry to a local LGTM stack and visualized in Grafana.

The design adapts Grafana's GenAI Evaluations guidance—which uses OpenLIT for hallucination, bias, and toxicity—to open-source Grafana, Loki, Tempo, and Mimir/Prometheus. Grafana Cloud's prebuilt experience is not assumed to exist locally; equivalent dashboards, recording rules, and alerts will be provisioned as code.

### Initial success criteria

- `docker compose up --build` starts the complete stack.
- A user can ask a question in Streamlit and receive a streamed OpenAI response grounded in supplied local documents.
- The generation trace appears in Tempo with prompt/retrieval/generation spans and GenAI semantic attributes.
- A background worker evaluates the answer on seven pillars and links results to the generation trace.
- Evaluation scores are visible as low-cardinality metrics; detailed explanations and inputs are searchable in Loki and trace spans.
- Grafana starts with provisioned datasources and useful dashboards, requiring no manual configuration.
- Secrets and configurable URLs/models live only in `.env`; `.env.example` contains safe placeholders and `.env` is gitignored.

## 2. Proposed architecture

```text
Browser
  -> Streamlit app
       -> local retrieval/index (small, deterministic demo corpus)
       -> OpenAI generation model (streaming)
       -> OTLP -> OpenTelemetry Collector/Alloy
       -> evaluation job queue
                         |
                         v
                   evaluator worker
                     -> OpenAI judge model
                     -> OTLP -> OpenTelemetry Collector/Alloy

Collector/Alloy
  -> Tempo (traces)
  -> Loki (logs and detailed evaluation records)
  -> Prometheus or Mimir (metrics)

Grafana -> provisioned Tempo, Loki, and Prometheus/Mimir datasources
```

### Compose services

1. `streamlit-app`: UI, RAG retrieval, OpenAI generation, instrumentation, and job submission.
2. `evaluator-worker`: consumes completed generations and runs structured judge calls.
3. `redis`: durable-enough local queue and retry/dead-letter support. For the smallest demo, this can begin as Redis Streams.
4. `otel-collector` or `alloy`: one OTLP endpoint for app and worker; batches, enriches, and routes telemetry.
5. `tempo`: trace storage and TraceQL.
6. `loki`: logs and detailed evaluation records.
7. `prometheus`: simplest local metrics backend. Mimir can be an optional Compose profile when testing a closer LGTM topology.
8. `grafana`: provisioned datasources, dashboards, correlations, recording rules, and alerts.

Use pinned image and Python dependency versions. Add health checks, `depends_on` health conditions where useful, named volumes, resource limits, and separate `app`, `observability`, and `optional-mimir` Compose profiles if startup weight becomes an issue.

## 3. Evaluation model: seven pillars

Each evaluator returns strict structured JSON with `score` (0.0–1.0, higher is better), `pass` (boolean), `reason`, `evidence`, `judge_model`, `rubric_version`, and `evaluation_latency_ms`.

| Pillar | Inputs | Meaning | Initial pass threshold |
|---|---|---|---:|
| Groundedness / faithfulness | response + retrieved contexts | Claims are supported by the supplied context | 0.80 |
| Hallucination avoidance | question + response + contexts | No fabricated, contradictory, or unsupported claims | 0.80 |
| Answer relevance | question + response | Directly addresses the user's intent without diversion | 0.75 |
| Context relevance | question + each retrieved chunk | Retrieval supplied useful evidence; supports RAG diagnosis | 0.70 |
| Completeness / correctness | question + response + optional reference answer | Covers key facts and is correct where a reference exists | 0.75 |
| Safety / toxicity | question + response | Avoids harmful, abusive, threatening, or disallowed content | 0.95 |
| Bias / fairness | question + response | Avoids unjustified stereotypes or disparate treatment | 0.95 |

Notes:

- Groundedness and hallucination are related but intentionally distinct: groundedness scores evidence support; hallucination avoidance detects invented or contradictory claims.
- Correctness is strongest for a curated golden dataset. In free-form production traffic it should be marked `not_applicable` when neither authoritative context nor a reference answer exists.
- OpenLIT's built-in hallucination, toxicity, and bias evaluators can be used behind a common adapter. Custom structured judge prompts cover the other four pillars. This keeps the framework replaceable and allows later comparison against deterministic or open-source evaluators.
- Store rubric prompts in versioned files, use deterministic settings where supported, validate JSON against a Pydantic model, and retry only malformed/transient judge calls.
- Never combine the seven scores into an unqualified average. Publish individual pillars plus a configurable weighted quality index, and always preserve `not_applicable` separately from failure.

## 4. Request and evaluation lifecycle

1. Generate a `conversation_id`, `request_id`, and root trace.
2. Record a retrieval span containing document IDs, chunk ranks, and similarity scores. Avoid high-cardinality text in metric labels.
3. Stream the OpenAI response while recording model, token counts, time-to-first-token, total latency, status, and estimated cost.
4. Persist or enqueue an immutable evaluation envelope: IDs, question, response, contexts, model metadata, timestamps, and optional reference answer.
5. Return control to the user immediately after generation; evaluation is never on the UI critical path.
6. Worker consumes the envelope, applies sampling and eligibility rules, runs evaluators with bounded concurrency, and emits one parent evaluation span plus child spans per pillar.
7. Emit:
   - metrics for aggregate trends and alerts;
   - structured logs for reason/evidence and failure investigation;
   - spans for end-to-end correlation and model-call diagnostics.
8. Link evaluation traces to the originating trace using an OpenTelemetry span link and shared `request_id`/`conversation_id`, since asynchronous work cannot reliably remain in the original span tree.

## 5. Telemetry contract

Follow OpenTelemetry GenAI semantic conventions where stable, with a namespaced custom schema for evaluation data.

### Resource attributes

`service.name`, `service.version`, `deployment.environment`, `gen_ai.system`, `eval.framework`, and `eval.rubric.version`.

### Core spans

- `chat.request`
- `rag.retrieve`
- `gen_ai.chat`
- `eval.run`
- `eval.pillar.<name>`

Useful attributes include `gen_ai.request.model`, `gen_ai.response.model`, token usage, finish reason, retrieval count, `eval.pillar`, `eval.score`, `eval.pass`, `eval.sampled`, and `eval.error.type`.

### Metrics

- `genai_requests_total{model,status}`
- `genai_request_duration_seconds{model}`
- `genai_time_to_first_token_seconds{model}`
- `genai_tokens_total{model,direction}`
- `genai_estimated_cost_usd_total{model}`
- `genai_eval_runs_total{pillar,status,pass}`
- `genai_eval_score{pillar,model,rubric_version}` as a histogram, not labels containing raw scores
- `genai_eval_duration_seconds{pillar,judge_model}`
- `genai_eval_queue_depth`
- `genai_eval_queue_age_seconds`
- `genai_eval_errors_total{pillar,error_type}`

Do not put `request_id`, prompts, responses, reasons, user IDs, or document text in metric labels. Exemplars should connect metric outliers to traces.

### Privacy defaults

- Make prompt/response/context capture opt-in with `CAPTURE_CONTENT=false` by default.
- Redact common secrets and PII before telemetry export.
- Store detailed content only in Loki/Tempo with explicit retention; never log the OpenAI API key.
- Hash or pseudonymize user/session identity and document identifiers.

## 6. Grafana experience

Provision three dashboards:

1. **GenAI Overview**: traffic, errors, latency, TTFT, tokens, estimated cost, model split, and trace exemplars.
2. **Evaluation Quality**: pass rate and score distribution per pillar, weighted quality index, trends by generation model/judge/rubric version, queue delay, evaluator errors, and a table linking failed evaluations to traces/logs.
3. **RAG Diagnostics**: groundedness versus context relevance, retrieval scores, retrieved chunk count, hallucination rate, and slow/failed retrieval traces.

Provision datasource correlations so a trace can open related Loki logs using `trace_id`, and dashboard data links can open Tempo using the evaluation's originating trace ID. Add initial alerts for sustained hallucination failures, groundedness regression, toxicity/bias failures, evaluation pipeline failures, and excessive queue age. Require a minimum sample count before quality alerts fire.

## 7. Configuration and secrets

Create `.env.example` with no real secrets:

```dotenv
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
GENERATION_MODEL=<generation-model>
JUDGE_MODEL=<judge-model>

OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_SERVICE_NAME=streamlit-genai-app
CAPTURE_CONTENT=false
EVAL_SAMPLE_RATE=1.0
EVAL_MAX_CONCURRENCY=4
EVAL_RUBRIC_VERSION=v1
REDIS_URL=redis://redis:6379/0

GRAFANA_URL=http://grafana:3000
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=
TEMPO_URL=http://tempo:3200
LOKI_URL=http://loki:3100
PROMETHEUS_URL=http://prometheus:9090
```

Validate required variables at startup and fail with clear names, never values. The host-facing URLs used by a browser may need separate variables from internal Compose URLs. Prefer Docker secrets for any later production adaptation; `.env` is acceptable only for this local reference setup.

## 8. Suggested repository layout

```text
.
├── compose.yaml
├── .env.example
├── .gitignore
├── Makefile
├── README.md
├── app/
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── src/{ui.py,rag.py,generation.py,telemetry.py,schemas.py}
├── evaluator/
│   └── src/{worker.py,registry.py,openlit_adapter.py,custom_judges.py}
├── rubrics/v1/*.yaml
├── sample_data/{documents/,golden_dataset.jsonl}
├── observability/
│   ├── collector/config.yaml
│   ├── tempo/tempo.yaml
│   ├── loki/loki.yaml
│   ├── prometheus/prometheus.yaml
│   └── grafana/provisioning/{datasources,dashboards,alerting}/
└── tests/{unit,integration,e2e}/
```

## 9. Delivery phases

### Phase 0 — decisions and contracts

- Confirm the demo domain/corpus and golden questions.
- Freeze the evaluation envelope, Pydantic result schema, seven rubrics, score direction, thresholds, and sampling behavior.
- Decide whether the first implementation uses OpenLIT's three built-ins or uniform custom judge prompts behind the same adapter. Recommended: adapter plus OpenLIT built-ins, with contract tests so either can be swapped.

Exit: fixtures demonstrate good, bad, and `not_applicable` outputs for every pillar.

### Phase 1 — local LGTM foundation

- Build Compose for Grafana, Tempo, Loki, Prometheus, collector/Alloy, and Redis.
- Configure OTLP gRPC/HTTP ingestion and Grafana provisioning.
- Add health checks, persistent volumes, Make targets, `.env.example`, and `.gitignore`.

Exit: synthetic logs, traces, and metrics appear in each Grafana datasource after one command.

### Phase 2 — instrumented Streamlit traffic generator

- Add Streamlit chat/RAG flow and token streaming.
- Instrument HTTP/OpenAI calls and custom retrieval/request spans.
- Emit operational metrics and structured logs.
- Include a controlled traffic mode using golden questions, configurable concurrency, pacing, and expected answer/context IDs.

Exit: manual and generated traffic produces correlated telemetry without evaluations.

### Phase 3 — asynchronous evaluation pipeline

- Add queue, idempotency key (`request_id + rubric_version`), retries, dead-letter stream, and worker concurrency controls.
- Implement the seven evaluator adapters, structured result validation, sampling, and trace links.
- Emit evaluation metrics/logs/spans while controlling content capture.

Exit: every sampled successful response is evaluated once; provider or worker failures do not affect app responses.

### Phase 4 — dashboards and alerts

- Provision the three dashboards, metric recording rules, exemplars, log/trace correlations, and alerts.
- Add filters for app version, generation model, judge model, rubric version, environment, pillar, and dataset case.

Exit: an intentionally bad golden response causes visible pillar failures and a navigable path from aggregate metric to evaluation detail to generation trace.

### Phase 5 — verification and hardening

- Unit-test rubric parsing, thresholds, redaction, sampling, and idempotency.
- Integration-test OTLP export and queue retry/dead-letter behavior.
- Run a deterministic end-to-end golden set and compare dashboard/API queries to expected bounds.
- Test judge bias/variance by repeating a subset and tracking agreement; version changes require re-baselining.
- Document cost controls, retention, backup/reset, troubleshooting, and limitations.

Exit: clean-machine runbook passes and produces a repeatable evaluation report.

## 10. Important risks and mitigations

- **Judge is not ground truth:** calibrate against human-labeled examples, record judge/rubric versions, and track agreement and variance.
- **Judge self-preference:** use a different judge model or provider where possible and periodically compare judges.
- **Cost explosion:** async sampling, response-length caps, context truncation, batching where supported, concurrency/rate limits, and daily cost alerts.
- **Telemetry cardinality:** fixed label allowlist; put detailed dimensions in logs/spans.
- **Sensitive content leakage:** default-off content capture, redaction, retention limits, and synthetic demo data.
- **Grafana Cloud parity:** local open-source Grafana does not automatically provide Cloud's managed GenAI app/dashboard behavior; provision equivalent dashboards and rules explicitly.
- **OpenLIT/API drift:** pin versions and isolate it behind adapters and contract tests.
- **False quality averages:** report pillar distributions, sample counts, applicability, and confidence alongside any aggregate index.

## 11. Definition of done

- One documented command launches a healthy stack and another runs controlled traffic.
- No committed secrets; all external credentials and endpoints are configurable through `.env`.
- A single request is traceable from Streamlit through retrieval and generation to each asynchronous evaluation.
- Seven pillar results follow one validated/versioned contract.
- Metrics remain low cardinality and detailed reasons remain searchable.
- Dashboards and alerts are provisioned as code and survive container recreation.
- Automated tests cover good/bad/failed provider paths, and the golden dataset produces documented expected score ranges.

## 12. Recommended first implementation slice

Implement one vertical slice before all seven evaluators: Compose LGTM + collector, Streamlit RAG request, async queue, groundedness judge, and a single Grafana panel linked to the trace. Once correlation, schema, privacy, and retry behavior are proven end to end, add the remaining six pillars and full dashboards. This reduces the chance of building seven evaluators on an unstable telemetry contract.
