import os

# Keep API unit tests fast — skip model/Qdrant warmup
os.environ.setdefault("COMPLIANCEIQ_SKIP_WARMUP", "1")
os.environ.setdefault("ENABLE_RERANK", "false")
