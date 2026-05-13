# Mutual Fund Prospectus Analyzer

A Streamlit + FastAPI RAG application for analyzing mutual fund prospectus and factsheet PDFs.

The app validates uploaded PDFs, discovers sections dynamically using a vision model, processes the document with Docling, indexes chunks in ChromaDB, and lets users extract section summaries or ask questions over the document.

## What It Does

- Validates whether a PDF is a mutual fund document.
- Detects document sections and subsections dynamically.
- Converts the PDF into metadata-rich chunks with Docling.
- Stores chunks in ChromaDB using OpenAI embeddings.
- Retrieves and reranks relevant chunks for questions.
- Extracts section-wise summaries.
- Shows source chunks and PDF page highlights.

## Project Structure

```text
app.py                    Streamlit frontend
api/api.py                FastAPI backend
config.py                 Shared settings and model config
prompts.py                LLM prompts
src/document_scanner.py   PDF validation and section discovery
src/document_processor.py PDF parsing and chunking
src/rag_engine.py         Embeddings, retrieval, reranking, chat
src/section_extractor.py  Section extraction logic
docs/APP_FLOW.md          Detailed app flow documentation
```

## Setup

Create and activate the virtual environment, then install dependencies:

```bash
uv sync
source .venv/bin/activate
```

Create a `.env` file with your OpenAI key:

```text
OPENAI_API_KEY=your_api_key_here
```

## Run

Start the FastAPI backend:

```bash
uvicorn api.api:app --host 0.0.0.0 --port 8082 --reload
```

Start the Streamlit frontend in another terminal:

```bash
streamlit run app.py
```

Then open the Streamlit URL shown in the terminal and upload a PDF.

## App Flow

```text
PDF upload
  -> validation
  -> dynamic section discovery
  -> Docling processing and chunking
  -> ChromaDB indexing
  -> section extraction or chat
  -> answer with source chunks
```

## API Base URL

The Streamlit app currently uses:

```python
API_BASE = "http://localhost:8082"
```

If you run the backend on a different port, update `API_BASE` in `app.py`.

## More Details

For the full architecture and step-by-step flow, read:

[docs/APP_FLOW.md](docs/APP_FLOW.md)
