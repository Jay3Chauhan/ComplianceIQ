"""
End-to-end smoke test against a running API (uses real Qdrant + Groq).

Usage:
  python scripts/smoke_test.py --base http://127.0.0.1:8000 --api-key <key> [--admin-key <key>]
"""

import argparse
import json
import sys
import time

import httpx


def stream_chat(client: httpx.Client, payload: dict) -> dict:
    events: list[dict] = []
    t0 = time.perf_counter()
    first_token = None
    with client.stream("POST", "/api/v1/chat/stream", json=payload, timeout=180) as res:
        res.raise_for_status()
        buffer = ""
        for chunk in res.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                frame, buffer = buffer.split("\n\n", 1)
                data = "\n".join(l[6:] for l in frame.splitlines() if l.startswith("data: "))
                if data:
                    event = json.loads(data)
                    if event["type"] == "token" and first_token is None:
                        first_token = time.perf_counter() - t0
                    events.append(event)
    types = [e["type"] for e in events]
    done = next((e for e in events if e["type"] == "done"), {})
    verification = next((e for e in reversed(events) if e["type"] == "verification"), None)
    retrieval = next((e for e in events if e["type"] == "retrieval"), {})
    return {
        "types": types,
        "done": done,
        "verification": verification,
        "retrieval": retrieval,
        "error": next((e for e in events if e["type"] == "error"), None),
        "ttft_s": round(first_token, 2) if first_token else None,
        "total_s": round(time.perf_counter() - t0, 2),
    }


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + detail) if detail else ''}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--admin-key")
    args = ap.parse_args()

    headers = {"X-API-Key": args.api_key, "X-User-Id": "smoke-test"}
    client = httpx.Client(base_url=args.base, headers=headers, timeout=60)
    results: list[bool] = []

    r = client.get("/api/v1/ready")
    results.append(check("ready", r.status_code == 200, json.dumps(r.json()["checks"])[:200]))

    s = stream_chat(client, {"question": "What are the periodic KYC update timelines for different risk categories?",
                             "category": "RBI"})
    d, v = s["done"], s["verification"] or {}
    results.append(check(
        "grounded answer", d.get("mode") == "regulatory" and len(s["retrieval"].get("sources", [])) > 0,
        f"mode={d.get('mode')} verification={v.get('status')} score={v.get('score')} "
        f"confidence={d.get('confidence')} ttft={s['ttft_s']}s total={s['total_s']}s",
    ))
    print("      answer:", (d.get("answer") or "")[:300].replace("\n", " "), "…")
    conv_id, msg_id = d.get("conversation_id"), d.get("message_id")

    s = stream_chat(client, {"question": "And what about for low risk customers?", "conversation_id": conv_id})
    results.append(check(
        "follow-up rewrite", s["done"].get("mode") == "regulatory",
        f"standalone='{s['retrieval'].get('standalone_question')}' total={s['total_s']}s",
    ))

    s = stream_chat(client, {"question": "What is the GST rate on restaurant services?", "answer_mode": "regulatory",
                             "save": False})
    results.append(check("out-of-scope refused", s["done"].get("mode") == "not_found",
                         f"gate={s['retrieval'].get('gate_score')}"))

    s = stream_chat(client, {"question": "What is a systematic investment plan?", "save": False})
    results.append(check("auto → general fallback", s["done"].get("mode") in ("general", "regulatory"),
                         f"mode={s['done'].get('mode')}"))

    docs = client.get("/api/v1/documents").json()
    results.append(check("documents", len(docs) >= 5 and all(d["indexed"] for d in docs if d["has_file"]),
                         f"{len(docs)} docs, {sum(d['chunks'] for d in docs)} chunks"))
    page = client.get(f"/api/v1/documents/{docs[0]['doc_id']}/pages/5").json()
    results.append(check("document page", "passages" in page, f"{len(page.get('passages', []))} passages"))
    outline = client.get(f"/api/v1/documents/{docs[0]['doc_id']}/outline").json()
    results.append(check("document outline", len(outline.get("sections", [])) > 0,
                         f"{len(outline.get('sections', []))} sections"))

    sr = client.post("/api/v1/search", json={"query": "Key Fact Statement", "top_k": 3}).json()
    results.append(check("search", len(sr["results"]) > 0 and sr["grounded"],
                         sr["results"][0]["citation"] if sr["results"] else ""))

    if msg_id:
        fb = client.put(f"/api/v1/messages/{msg_id}/feedback", json={"rating": 1})
        results.append(check("feedback", fb.status_code == 200))

    convs = client.get("/api/v1/conversations").json()
    results.append(check("conversation list", convs["total"] >= 1, f"total={convs['total']}"))

    if args.admin_key:
        st = client.get("/api/v1/admin/stats", headers={"X-Admin-Key": args.admin_key}).json()
        results.append(check("admin stats", "usage" in st, json.dumps(st["usage"]["by_mode"])))

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
