"""Quick connectivity and rate-limit check for the configured Groq models.

Usage: python -m scripts.check_llm [extra-model ...]
"""

import sys
import time

from config import settings
from llm.groq_client import _model_kwargs, complete_json, get_groq_client


def main() -> None:
    models = [settings.groq_model, settings.groq_fast_model, *settings.fallback_model_list, *sys.argv[1:]]
    for name in dict.fromkeys(models):
        t = time.perf_counter()
        raw = get_groq_client().chat.completions.with_raw_response.create(
            model=name,
            messages=[{"role": "user", "content": "Reply with exactly: OK [1]"}],
            **_model_kwargs(name, 50),
        )
        resp = raw.parse()
        h = raw.headers
        data = complete_json(
            [
                {"role": "system", "content": "Respond with JSON only."},
                {"role": "user", "content": 'Return exactly {"results": [{"id": 1, "supported": true}]}'},
            ],
            model=name,
            allow_fallback=False,
        )
        print(
            f"{name:22} {resp.choices[0].message.content!r:10} json_ok={bool(data.get('results'))} "
            f"rpm={h.get('x-ratelimit-limit-requests')} tpm={h.get('x-ratelimit-limit-tokens')} "
            f"{time.perf_counter() - t:.1f}s"
        )


if __name__ == "__main__":
    main()
