"""Prints every API route from the OpenAPI schema (method, path, summary, request body, response)."""

from api.main import app


def _ref(schema: dict | None) -> str:
    if not schema:
        return ""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if schema.get("type") == "array":
        return f"list[{_ref(schema.get('items'))}]"
    return schema.get("type", "")


def main() -> None:
    spec = app.openapi()
    for path, ops in spec["paths"].items():
        for method, op in ops.items():
            body = op.get("requestBody", {}).get("content", {})
            req = ", ".join(f"{ct}:{_ref(c.get('schema'))}" for ct, c in body.items())
            ok = next((r for code, r in op.get("responses", {}).items() if code.startswith("2")), {})
            resp = _ref(ok.get("content", {}).get("application/json", {}).get("schema"))
            params = ",".join(p["name"] for p in op.get("parameters", []) if p["in"] in ("query", "path"))
            print(f"{method.upper():6} {path:48} params=[{params}] body=[{req}] -> {resp} | {op.get('summary', '')}")


if __name__ == "__main__":
    main()
