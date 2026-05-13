# Mutual Fund Prospectus Analyzer - App Flow

This project is a Retrieval-Augmented Generation application for mutual fund prospectus and factsheet PDFs.

The app lets a user upload a PDF, validates whether it is a mutual fund document, discovers the document sections dynamically, chunks and indexes the PDF, extracts section-wise summaries, and answers user questions using RAG.

## High-Level Architecture

```text
Streamlit UI
    |
    | HTTP requests
    v
FastAPI backend
    |
    | validate + scan + process + index
    v
DocumentScanner + DocumentProcessor + RagEngine + SectionExtractor
    |
    | embeddings and retrieval
    v
ChromaDB + OpenAI models
```

Main layers:

- `app.py`: Streamlit frontend.
- `api/api.py`: FastAPI backend.
- `src/document_scanner.py`: Vision-based validation and dynamic section discovery.
- `src/document_processor.py`: Docling-based PDF parsing and chunk generation.
- `src/rag_engine.py`: Embedding, ChromaDB indexing, retrieval, reranking, and chat.
- `src/section_extractor.py`: Section-level extraction using discovered sections and RAG.
- `prompts.py`: LLM prompts used by scanner, consolidation, extraction, reranking, and chat.
- `config.py`: Shared configuration such as model names, thresholds, and ChromaDB settings.

## User Flow

1. User starts the backend API.

   ```bash
   uvicorn api.api:app --host 0.0.0.0 --port 8082 --reload
   ```

2. User starts the Streamlit app.

   ```bash
   streamlit run app.py
   ```

3. User uploads a PDF in the sidebar.

4. Streamlit sends the PDF to:

   ```text
   POST /upload
   ```

5. Backend validates the document.

6. If validation passes, backend discovers sections.

7. Backend processes the PDF into chunks.

8. Backend indexes chunks in ChromaDB.

9. Streamlit loads discovered sections and shows them in the sidebar.

10. User can:

    - view PDF pages
    - extract one section
    - extract all sections
    - ask questions in chat
    - jump to source pages/chunks

## Upload Pipeline

The most important flow starts in `api/api.py` inside `upload_document()`.

```text
POST /upload
    |
    v
Save uploaded PDF to temp path
    |
    v
DocumentScanner.validate_document()
    |
    v
DocumentScanner.discover_sections()
    |
    v
DocumentProcessor.process_document()
    |
    v
RagEngine.index_chunks()
    |
    v
SectionExtractor(...)
    |
    v
Store all runtime objects in _state
```

The backend keeps the processed document in an in-memory `_state` dictionary. This means the app is simple and good for local/demo use, but it is not designed for multiple users or multiple documents at the same time.

## Step 1: Document Validation

File:

```text
src/document_scanner.py
```

Method:

```python
validate_document(pdf_path)
```

Purpose:

Checks whether the uploaded PDF looks like a mutual fund document.

How it works:

1. Counts the total pages.
2. Scans only the first `VALIDATION_MAX_PAGES`.
3. Renders each page as a PNG image using PyMuPDF.
4. Converts the image into base64.
5. Sends the image plus `DOCUMENT_VALIDATION_PROMPT` to the vision model.
6. Expects JSON like:

   ```json
   {"is_mf_document": true, "confidence": "high", "reason": "brief explanation"}
   ```

7. Starts with `VALIDATION_INITIAL_SCORE`.
8. Adds `VALIDATION_SCORE_DELTA` for each page that looks like mutual fund content.
9. Subtracts `VALIDATION_SCORE_DELTA` for each page that does not.
10. Accepts the document if final score is at least `VALIDATION_THRESHOLD`.

Config values:

```python
VALIDATION_INITIAL_SCORE = 50
VALIDATION_THRESHOLD = 65
VALIDATION_SCORE_DELTA = 10
VALIDATION_MAX_PAGES = 5
```

If the score is below the threshold, the backend returns HTTP `422`, and the Streamlit app shows a rejection message.

## Step 2: Dynamic Section Discovery

File:

```text
src/document_scanner.py
```

Method:

```python
discover_sections(pdf_path)
```

Purpose:

Finds the sections and subsections in the PDF without using a hardcoded section list.

How it works:

1. Loops through every PDF page.
2. Renders the page as a base64 PNG image.
3. Builds a page-scanning prompt from `PAGE_SECTION_SCAN_PROMPT`.
4. Adds recent previous-page context using `SlidingWindowMemory`.
5. Sends prompt plus page image to the vision model.
6. Parses page-level JSON containing:

   - page number
   - sections found
   - section titles
   - descriptions
   - keywords
   - subsections
   - continuation flag
   - page summary

7. Stores short AI summaries in sliding-window memory.
8. After all pages are scanned, calls `_consolidate_sections()`.

## Sliding Window Memory

Class:

```python
SlidingWindowMemory
```

Purpose:

Keeps recent page summaries so the model can understand continuity across pages.

Example:

If page 4 continues a section from page 3, the model can use recent context to mark it as a continuation.

Important detail:

Each page exchange stores:

```text
HumanMessage: "Scan page N"
AIMessage: "Page N summary and sections"
```

For `window_size = 3`, the memory stores the last 3 exchanges, which means the last 6 messages.

## Step 3: Section Consolidation

File:

```text
src/document_scanner.py
```

Method:

```python
_consolidate_sections(page_analysis)
```

Purpose:

The page scanner gives page-by-page results, which may contain duplicates or continuation sections. Consolidation merges them into one clean document-level section map.

Example before consolidation:

```text
Page 2: Risk Factors
Page 3: Risk Factors continued
Page 4: Fees and Expenses
```

Example after consolidation:

```python
{
    "risk_factors": {
        "title": "Risk Factors",
        "description": "...",
        "subsections": [...],
        "keywords": [...],
        "pages": [2, 3]
    },
    "fees_and_expenses": {
        "title": "Fees and Expenses",
        "description": "...",
        "subsections": [...],
        "keywords": [...],
        "pages": [4]
    }
}
```

This uses `SECTION_CONSOLIDATION_PROMPT`.

## Step 4: PDF Processing And Chunking

File:

```text
src/document_processor.py
```

Main class:

```python
DocumentProcessor
```

Main method:

```python
process_document(pdf_path)
```

Purpose:

Converts the PDF into structured text chunks with metadata.

How it works:

1. Initializes Docling `DocumentConverter`.
2. Converts the PDF into a structured Docling document.
3. Initializes Docling `HybridChunker`.
4. Generates semantic chunks.
5. Extracts metadata for each chunk.
6. Returns a list of `ChunkWithMetaData`.

The chunk object contains:

```python
chunk_id
text
page_number
bbox
element_type
headings
```

Why custom `ChunkWithMetaData` exists:

Docling metadata is nested and Docling-specific. `ChunkWithMetaData` normalizes it into a simple structure that the rest of the RAG pipeline can use easily.

## Step 5: Indexing Chunks In ChromaDB

File:

```text
src/rag_engine.py
```

Main class:

```python
RagEngine
```

Method:

```python
index_chunks(chunks)
```

Purpose:

Stores document chunks in a vector database so they can be retrieved by semantic similarity.

How it works:

1. Creates OpenAI embeddings using `OpenAIEmbeddings`.
2. Converts each `ChunkWithMetaData` into a LangChain `Document`.
3. Stores chunk text as `page_content`.
4. Stores metadata such as:

   - chunk id
   - page number
   - element type
   - headings
   - bounding box

5. Creates a ChromaDB vector store using `Chroma.from_documents()`.

LangChain `Document` shape:

```python
Document(
    page_content="chunk text here",
    metadata={
        "chunk_id": 1,
        "page_number": 3,
        "element_type": "text",
        "headings": "...",
        "bbox": "..."
    }
)
```

## Step 6: Retrieval And Reranking

File:

```text
src/rag_engine.py
```

Methods:

```python
retrieve(query)
rerank(query, documents)
retrieve_and_rerank(query)
```

Flow:

```text
User query
    |
    v
ChromaDB similarity search
    |
    v
Initial top chunks
    |
    v
LLM reranking
    |
    v
Best final chunks
```

Initial retrieval finds chunks using vector similarity.

Reranking asks the LLM to score the retrieved chunks for relevance to the query. If reranking fails, the code falls back to the original retrieval order.

Returned chunk result includes:

```python
text
score
chunk_id
page_number
element_type
headings
bbox
```

## Step 7: Chat Over The Document

File:

```text
src/rag_engine.py
```

Method:

```python
chat(query)
```

Purpose:

Answers a user question using only retrieved document chunks.

How it works:

1. Retrieves and reranks chunks for the user query.
2. Builds a context string from those chunks.
3. Inserts context and query into `CHAT_SYSTEM_PROMPT`.
4. Calls the LLM.
5. Returns:

   - answer text
   - source chunks

The Streamlit chat UI displays the answer and lets the user inspect source chunks.

## Step 8: Section Extraction

File:

```text
src/section_extractor.py
```

Class:

```python
SectionExtractor
```

Method:

```python
extract_section(section_key)
```

Purpose:

Extracts structured content for a discovered section.

How it works:

1. Receives a section key, such as `risk_factors`.
2. Looks up the discovered section config:

   ```python
   title
   description
   subsections
   keywords
   pages
   ```

3. Builds a search query using title, description, subsections, and keywords.
4. Calls `RagEngine.search_for_section()`.
5. Retrieves relevant chunks.
6. Builds an extraction prompt using `SECTION_EXTRACTION_PROMPT`.
7. Calls the LLM to produce a section summary.
8. Performs focused retrieval for each subsection.
9. Stores the result as `SectionContent`.

Returned section shape:

```python
{
    "section_key": "...",
    "title": "...",
    "description": "...",
    "summary": "...",
    "subsections": [
        {
            "title": "...",
            "content": "...",
            "chunks": [...]
        }
    ],
    "all_chunks": [...]
}
```

## API Endpoints

### Status

```text
GET /status
```

Returns whether a document is loaded, number of chunks, total pages, validation result, and extracted section keys.

### Upload

```text
POST /upload
```

Runs the full backend pipeline:

```text
validate -> discover sections -> process chunks -> index chunks -> create section extractor
```

### Page Count

```text
GET /page-count
```

Returns total pages in the uploaded PDF.

### Page Image

```text
GET /page/{page_num}
```

Renders a page as base64 PNG.

Optional query params:

```text
zoom
bbox
```

If `bbox` is provided, the backend highlights that region on the rendered page.

### Sections

```text
GET /sections
```

Returns dynamically discovered sections.

### Extract One Section

```text
POST /extract-section
```

Body:

```json
{"section_key": "risk_factors"}
```

Extracts one section using RAG and LLM summarization.

### Extract All Sections

```text
POST /extract-all
```

Extracts every discovered section.

### Get Extracted Sections

```text
GET /extracted-sections
```

Returns cached section extraction results.

### Chat

```text
POST /chat
```

Body:

```json
{"query": "What is the expense ratio?"}
```

Returns:

```python
answer
sources
```

### Chunks

```text
GET /chunks
GET /chunks?page=3
```

Returns all chunks, or only chunks from a specific page.

## Frontend Flow

File:

```text
app.py
```

The Streamlit app manages UI state using `st.session_state`.

Important state values:

```python
document_processed
current_page
total_pages
highlight_bbox
selected_section
selected_subsection
chat_history
extracted_sections
discovered_sections
validation_result
```

Main frontend functions:

- `process_uploaded_document()`: sends uploaded PDF to `/upload`.
- `load_section_definitions()`: fetches `/sections`.
- `render_pdf_page()`: calls `/page/{page_num}`.
- `extract_section_content()`: calls `/extract-section`.
- `extract_all_sections()`: calls `/extract-all`.
- `navigate_to_chunk()`: jumps viewer to a chunk page and stores its bbox.
- `send_chat_message()`: calls `/chat`.
- `render_sidebar()`: upload, validation score, section navigation.
- `render_document_viewer()`: page navigation and image display.
- `render_section_content()`: extracted summaries and subsection sources.
- `render_chatbot()`: chat interface and source viewing.

## PDF Viewer And Source Navigation

When a retrieved chunk has a bounding box:

1. Streamlit stores the bbox in `st.session_state.highlight_bbox`.
2. Streamlit calls:

   ```text
   GET /page/{page_num}?bbox=...
   ```

3. FastAPI renders the page with PyMuPDF.
4. If bbox is present, PIL draws a red rectangle.
5. Streamlit displays the highlighted page.

This connects RAG answers back to the original PDF location.

## Prompt Usage

File:

```text
prompts.py
```

Prompts:

- `DOCUMENT_VALIDATION_PROMPT`: decides if a page belongs to a mutual fund document.
- `PAGE_SECTION_SCAN_PROMPT`: identifies sections and subsections on a page image.
- `SECTION_CONSOLIDATION_PROMPT`: merges page-level findings into final document sections.
- `SECTION_EXTRACTION_PROMPT`: extracts content for one discovered section.
- `CHAT_SYSTEM_PROMPT`: answers user questions using retrieved chunks.
- `RERANK_PROMPT`: scores retrieved chunks for relevance.

## Data Flow Summary

```text
PDF upload
    |
    v
Temporary PDF path
    |
    v
Vision validation
    |
    v
Dynamic section discovery
    |
    v
Docling conversion
    |
    v
Semantic chunks with metadata
    |
    v
LangChain Documents
    |
    v
OpenAI embeddings
    |
    v
ChromaDB vector store
    |
    v
Retrieval + reranking
    |
    v
Section extraction or chat answer
    |
    v
Streamlit display with source navigation
```

## Important Runtime Notes

- The backend API base URL in `app.py` is currently:

  ```python
  API_BASE = "http://localhost:8082"
  ```

  So the backend should run on port `8082` unless you update `API_BASE`.

- The API keeps state in memory. Restarting the backend clears uploaded document state.

- The app currently processes one document at a time.

- OpenAI API key must be available through `.env` or environment variables.

- ChromaDB persists under `CHROMA_PERSIST_DIR` from `config.py`.

- Some operations call OpenAI models, so upload, section extraction, reranking, and chat require network/API access.

## Short Explanation

In simple terms, the app does this:

1. Takes a mutual fund PDF from the user.
2. Checks if it is really a mutual fund document.
3. Uses a vision model to understand the document's section structure.
4. Uses Docling to split the PDF into searchable chunks.
5. Stores those chunks in ChromaDB using embeddings.
6. Retrieves the best chunks when the user asks a question or extracts a section.
7. Uses an LLM to generate the final answer or section summary.
8. Shows the answer with source chunks and lets the user jump back to the PDF page.
