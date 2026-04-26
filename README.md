# ComplianceIQ

ComplianceIQ is a **production-grade RAG (Retrieval-Augmented Generation) system** for Indian financial regulations.
It ingests RBI Master Directions, SEBI circulars, and Account Aggregator (AA) guidelines as PDFs, indexes them in Qdrant, and answers compliance questions with **grounded citations (document + circular ID + page number)**.

## Why this exists

Compliance teams spend hours searching PDFs, circular archives, and internal notes. ComplianceIQ turns your curated regulatory corpus into a fast, auditable Q&A system that:

- produces **citation-backed answers** suitable for internal review,
- reduces time-to-answer for policy interpretation and checks,
- keeps answers anchored to the exact paragraph/page that was retrieved.

## Key features

- **Grounded answers with citations** (document name, circular ID, page number)
- **PDF ingestion pipeline**: parse → chunk → embed → upsert to Qdrant
- **Local embeddings** with `BAAI/bge-small-en-v1.5` (free, no embedding API cost)
- **Fast retrieval** using Qdrant Cloud (payload indexes for filtering)
- **REST API** via FastAPI (`/api/query`, `/api/ingest`, `/api/documents`, `/api/health`)
- **Chat UI** via Streamlit with source snippets and relevance scores
- **Evaluation hooks** using RAGAS for faithfulness/relevancy checks

## Primary use-cases

- **Fintech product compliance**: onboarding flows, KYC/AML checks, disclosures, grievance policies
- **Digital lending**: KFS requirements, FLDG, reporting/consent obligations (depending on ingested docs)
- **Broker / MF operations**: process adherence to master circulars, audit prep
- **Account Aggregator**: consent artefacts, data-sharing constraints, technical spec lookups
- **Internal audits / QA**: “show me the page and circular reference” type questions

## Benefits (what you get)

- **Auditability**: citations per claim make it easier to verify internally
- **Lower hallucination risk**: system prompt enforces context-only answers and “not found” behavior
- **Reusable corpus**: ingest once, query repeatedly across teams
- **Faster compliance turnaround**: reduces manual PDF scanning time

## Architecture (high level)

```
User Question
  → BGE query embedding
  → Qdrant similarity search (+ optional filter)
  → LLM (Groq LLaMA) with retrieved context
  → Answer + citations + source snippets
```

## Tech stack

| Layer | Choice |
|------|--------|
| LLM | Groq (`llama-3.3-70b-versatile`) |
| Embeddings | `sentence-transformers` + `BAAI/bge-small-en-v1.5` (local) |
| Vector DB | Qdrant Cloud |
| API | FastAPI |
| UI | Streamlit |
| PDF parsing | PyMuPDF + pdfplumber fallback |
| Eval | RAGAS |

## Repo layout

```
ComplianceIQ/
├── config.py
├── requirements.txt
├── .env.example
├── data/
│   ├── documents/               # PDFs (gitignored)
│   └── document_registry.json   # registry metadata
├── ingestion/                   # parse → chunk → embed → store
├── retrieval/                   # Qdrant retrieval
├── llm/                         # prompt templates + Groq client
├── api/                         # FastAPI app + routes
├── frontend/                    # Streamlit UI
├── evaluation/                  # RAGAS evaluation
└── tests/
```

## Setup (Windows / PowerShell)

### 1) Create venv + install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2) Configure environment

- Copy `.env.example` → `.env`
- Fill in your keys (Groq + Qdrant Cloud)

Important:
- `.env` is **gitignored** by default.
- never paste keys into commits/issues.

### 3) Add PDFs + update the registry

- Put your PDFs in `data/documents/`
- Ensure filenames match entries in `data/document_registry.json`

### 4) Ingest PDFs to Qdrant

```powershell
python -m ingestion.run_ingestion
```

### 5) Run API + UI

```powershell
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

In a second terminal:

```powershell
streamlit run frontend/app.py
```

## API usage

### POST `/api/query`

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the KYC requirements for digital lending?",
    "category": "RBI",
    "top_k": 5
  }'
```

### Admin ingestion: POST `/api/ingest`

```bash
curl -X POST http://localhost:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{ "filename": "RBI_KYC_Master_Direction_2016.pdf" }'
```

## Grounding & safety notes

- ComplianceIQ is designed to answer **only from the currently loaded regulatory documents**.
- If information is not found in retrieved context, it returns a “not found” style response.
- This is an **internal assistance tool**. Always validate outcomes with your compliance/legal process and regulator sources.

## Troubleshooting

- **Qdrant auth/URL issues**: confirm `QDRANT_URL` and `QDRANT_API_KEY` in `.env`
- **No results**: confirm you ingested documents and the `QDRANT_COLLECTION` name matches
- **PDF not ingested**: ensure `data/document_registry.json` includes the PDF filename exactly

## Contributing / Branching

See `CONTRIBUTING.md` for the repo workflow (branches, PR checklist, commit conventions).

## License

MIT. See `LICENSE`.
