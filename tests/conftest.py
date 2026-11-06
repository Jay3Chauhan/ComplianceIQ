import os
import tempfile
from pathlib import Path

# Must be set before any project module imports `config.settings`.
_tmp = Path(tempfile.mkdtemp(prefix="complianceiq-tests-"))
os.environ["COMPLIANCEIQ_SKIP_WARMUP"] = "1"
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["APP_ENV"] = "development"
os.environ["API_KEYS"] = "test-key"
os.environ["ADMIN_API_KEY"] = "admin-key"
os.environ["ENABLE_RERANK"] = "false"
os.environ["ENABLE_LLM_VERIFIER"] = "false"
os.environ["ENABLE_QUERY_REWRITE"] = "false"
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["ENABLE_FOLLOWUPS"] = "false"
os.environ["ENABLE_LLM_TITLES"] = "false"
if os.getenv("RUN_INTEGRATION") != "1":
    # Unit runs never touch real services; integration runs read credentials from .env
    os.environ.setdefault("GROQ_API_KEY", "test")
    os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
    os.environ.setdefault("QDRANT_API_KEY", "test")

import pytest  # noqa: E402

API_HEADERS = {"X-API-Key": "test-key", "X-User-Id": "user-a"}


@pytest.fixture
def sample_chunks() -> list[dict]:
    return [
        {
            "chunk_id": "c1", "doc_id": "kyc", "doc_name": "RBI Master Direction on KYC 2016",
            "circular_id": "RBI/DBR/2016", "category": "RBI", "section": "Chapter VI › 38 Periodic Updation",
            "page_number": 33, "date": "2016-02-25", "source_url": "https://rbi.org.in", "filename": "kyc.pdf",
            "chunk_text": "Periodic updation shall be carried out at least once in every two years for high risk "
                          "customers, once in every eight years for medium risk customers and once in every ten "
                          "years for low risk customers.",
            "relevance_score": 0.91, "citation": "RBI KYC | Page 33",
        },
        {
            "chunk_id": "c2", "doc_id": "kyc", "doc_name": "RBI Master Direction on KYC 2016",
            "circular_id": "RBI/DBR/2016", "category": "RBI", "section": "Chapter VI › 38 Periodic Updation",
            "page_number": 34, "date": "2016-02-25", "source_url": "", "filename": "kyc.pdf",
            "chunk_text": "The REs shall carry out PAN verification from the verification facility available "
                          "with the issuing authority.",
            "relevance_score": 0.62, "citation": "RBI KYC | Page 34",
        },
    ]
