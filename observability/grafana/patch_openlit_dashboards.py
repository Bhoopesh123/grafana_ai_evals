import json
import sys
from pathlib import Path


REPLACEMENTS = {
    '=~".*"': '=~".+"',
    "${metrics_datasource}": "prometheus",
    "${prometheus_datasource}": "prometheus",
    "${logs_datasource}": "loki",
    "${loki_datasource}": "loki",
    "${trace_datasource}": "tempo",
    "${traces_datasource}": "tempo",
    "${tempo_datasource}": "tempo",
    "${service_name}": ".+",
    "$service_name": ".+",
    "${deployment_environment}": ".+",
    "$deployment_environment": ".+",
    "${application}": ".+",
    "$application": ".+",
    "${environment}": ".+",
    "$environment": ".+",
}


def replace_variables(value):
    if isinstance(value, dict):
        return {key: replace_variables(item) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_variables(item) for item in value]
    if isinstance(value, str):
        for old, new in REPLACEMENTS.items():
            value = value.replace(old, new)
    return value


def patch_dashboard(path: Path) -> None:
    dashboard = json.loads(path.read_text())
    dashboard["time"] = {"from": "now-30m", "to": "now"}
    dashboard["refresh"] = "10s"
    dashboard = replace_variables(dashboard)
    dashboard.setdefault("templating", {})["list"] = [
        variable
        for variable in dashboard.get("templating", {}).get("list", [])
        if variable.get("name") == "traceId"
    ]
    dashboard["version"] = int(dashboard.get("version", 0)) + 1

    path.write_text(json.dumps(dashboard, indent=2) + "\n")


def main() -> None:
    dashboard_dir = Path(sys.argv[1])
    for path in dashboard_dir.glob("openlit-*.json"):
        patch_dashboard(path)


if __name__ == "__main__":
    main()
