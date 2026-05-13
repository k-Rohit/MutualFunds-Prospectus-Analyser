# Endpoints:
#   POST /upload              - Validate → scan → process → index
#   GET  /status              - Check state (includes validation info)
#   GET  /page-count          - Total pages in the loaded PDF
#   GET  /page/{page_num}     - Render a single PDF page as PNG
#   GET  /sections            - Return dynamically discovered sections
#   POST /extract-section     - Extract one section via RAG + LLM
#   POST /extract-all         - Extract all discovered sections
#   GET  /extracted-sections  - Return all previously extracted content
#   POST /chat                - Chat / Q&A over the document
#   GET  /chunks              - Get chunks (optionally filtered by page)


# Run with:  uvicorn api:app --host 0.0.0.0 --port 8082 --reload

import os
import io
import json
import shutil
import tempfile
import base64
import traceback
from typing import Optional, List, Dict

import fitz  # PyMuPDF – page rendering only
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.document_processor import DocumentProcessor
from src.document_scanner import DocumentScanner
from src.rag_engine import RagEngine
from src.section_extractor import SectionExtractor


app = FastAPI(
     title = "Mutual Funds Prospectus Analyser",
     description="REST API for processing, extracting, and querying mutual fund prospectus PDFs",
     version = "1.0.0"
)

# In-memory state.
# FastAPI request handlers do not automatically share per-document state.
# For this demo-style API, the most recently uploaded PDF, processed chunks,
# vector index, scanner, and extracted sections are kept here instead of a DB.
# This is simple and useful for local work, but it is single-process/single-user.
_state: Dict = {
    "pdf_path": None,
    "processor": None,
    "chunks": [],
    "rag_engine": None,
    "section_extractor": None,
    "scanner": None,
    "discovered_sections": {},
    "validation_result": {},
    "total_pages": 0,
}

def _is_loaded() -> bool:
    """Return True once a document has been uploaded, processed, and indexed."""
    return _state["rag_engine"] is not None

def _sanitize(obj):
    """Recursively convert to JSON-safe primitives."""
    
    # JSON null
    if obj is None:
        return None
    
    # int and bool are natively JSON-serializable.
    # bool must be checked before int because bool is a subclass of int —
    # if we checked int first, True/False would match it and still work,
    # but being explicit avoids subtle bugs.
    if isinstance(obj, (int, bool)):
        return obj
    
    # floats are JSON-safe UNLESS they are NaN or Infinity,
    # which are valid in Python but not in the JSON spec.
    # NaN is the only value in Python that is not equal to itself,
    # so "obj != obj" is a cheap way to detect it without importing math.
    if isinstance(obj, float):
        if obj != obj:  # NaN check
            return 0.0
        return obj
    
    # Strings are natively JSON-serializable.
    if isinstance(obj, str):
        return obj
    
    # Dicts are JSON objects, but keys must be strings.
    # str(k) forces any non-string key (int, enum, etc.) to a string,
    # and we recurse into values to sanitize them as well.
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    
    # Lists and tuples both map to JSON arrays.
    # Tuples are not JSON-serializable by default, so we convert them
    # to lists here while recursing into each element.
    if isinstance(obj, (list, tuple)):
        return [_sanitize(i) for i in obj]
    
    # Catch-all for anything else: custom class instances, Decimals,
    # enums, Paths, etc. stringify them so they don't crash serialization.
    return str(obj)

# Request schemas.
# These classes define the JSON body FastAPI expects for POST endpoints.
# FastAPI also uses them to generate OpenAPI/Swagger documentation.

class ChatRequest(BaseModel):
    # User question to answer using the indexed document chunks.
    query: str

class ExtractSectionRequest(BaseModel):
    # Key from /sections, for example "risk_factors" or "fees_and_expenses".
    section_key: str
    
# Endpoints

@app.get("/status", tags=["Status"])
def get_status():
    """Return the current processing state without triggering any new work."""
    # Extracted section content lives inside SectionExtractor, so collect only
    # the keys here to keep the status response compact.
    extracted = []
    if _state["section_extractor"]:
        extracted = list(_state["section_extractor"].extracted_sections.keys())
    return {
        "document_loaded": _is_loaded(),
        "total_pages": _state["total_pages"],
        "num_chunks": len(_state["chunks"]),
        "extracted_sections": extracted,
        "discovered_sections_count": len(_state["discovered_sections"]),
        "validation": _state.get("validation_result", {}),
    }

@app.post("/upload", tags=["Document"])
async def upload_document(file: UploadFile = File(...)):
     
     """
      Upload a PDF.  The pipeline:
      1. VALIDATE  – vision scan of first 5 pages (score ≥ 65 required)
      2. DISCOVER  – vision scan of all pages → section structure
      3. PROCESS   – Docling extraction + chunking
      4. INDEX     – embed chunks into ChromaDB

    If validation fails the response has HTTP 422 with score details.
    """
     if not file.filename.lower().endswith('.pdf'):
         raise HTTPException(status_code=400, detail="Only PDF files are accepted.")
     
     # Create a temporary directory to store the uploaded file.
     # We use a directory (not just a temp file) because downstream tools
     # may create additional files alongside the PDF during processing.
     tmp_dir = tempfile.mkdtemp()
    
     # Build the full path using the original filename so it is recognizable
     # in logs and error messages (e.g. /tmp/tmpA3x9kL/prospectus.pdf).
     tmp_path = os.path.join(tmp_dir, file.filename)
    
     # Write the uploaded file stream to disk.
     # file.file is the raw stream from the HTTP request — not a file on disk.
     # shutil.copyfileobj copies it in chunks rather than loading the entire
     # PDF into memory at once, which matters for large documents.
     # "wb" = write in binary mode, required for non-text files like PDFs.
     with open(tmp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
     
     try:
          # 1. Validate the uploaded PDF before doing expensive extraction.
          # The scanner uses a vision model on the first few pages and returns
          # a score; low-scoring documents are rejected as non-mutual-fund docs.
          scanner = DocumentScanner()
          is_valid, score, summary = scanner.validate_document(tmp_path)
          
          if not is_valid:
               # Store the failed validation result so /status can explain
               # why the current upload did not become the loaded document.
               _state["validation_result"] = scanner.validation_result
               raise HTTPException(
                    status_code=422,
                    detail={
                    "message": "Document validation failed – not a mutual fund document",
                    "validation": _sanitize(scanner.validation_result),
                },
               )
          # 2. Discover the document's natural section structure dynamically.
          # This avoids relying on a hardcoded list of mutual fund sections.
          discovered_sections = scanner.discover_sections(tmp_path)
          
          # 3. Convert the PDF into structured chunks with Docling metadata.
          # These chunks carry text, page number, headings, bbox, and type.
          processor = DocumentProcessor()
          chunks = processor.process_document(tmp_path)
          
          # 4. Embed and index chunks in ChromaDB for semantic retrieval.
          rag_engine = RagEngine()
          rag_engine.index_chunks(chunks=chunks)
          
          # 5. Build the section extractor on top of the RAG engine and the
          # discovered section definitions.
          section_extractor = SectionExtractor(rag_engine=rag_engine, discovered_sections=discovered_sections)
          
          # 6. Keep page count available for navigation/rendering endpoints.
          doc = fitz.open(tmp_path)
          total_pages = len(doc)
          doc.close()
          
          # 7. Persist everything needed by later API calls.
          _state.update({
          "pdf_path": tmp_path,
          "processor": processor,
          "chunks": chunks,
          "rag_engine": rag_engine,
          "section_extractor": section_extractor,
          "scanner": scanner,
          "discovered_sections": discovered_sections,
          "validation_result": scanner.validation_result,
          "total_pages": total_pages,
          })
          
          return {
          "message": "Document processed successfully",
          "filename": file.filename,
          "total_pages": total_pages,
          "num_chunks": len(chunks),
          "sections_discovered": len(discovered_sections),
          "validation": _sanitize(scanner.validation_result),
          }
     
     except HTTPException:
          # Preserve intentional FastAPI errors such as 400/422.
          raise
     
     except Exception as e:
        # Unexpected exceptions become HTTP 500, while the traceback remains
        # visible in server logs for debugging.
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
     
# PDF page rendering
@app.get("/page-count", tags=["Document"])
def page_count():
    """Return total page count for the currently loaded PDF."""
    if not _is_loaded():
        raise HTTPException(status_code=400, detail="No document loaded.")
    return {"total_pages": _state["total_pages"]}

@app.get("/page/{page_num}", tags=["Document"])
def get_page_image(
    page_num: int,
    zoom: float = Query(1.5),
    bbox: Optional[str] = Query(None),
):
    """Render a 1-indexed PDF page as base64 PNG, with optional bbox highlight."""
    if not _is_loaded():
        raise HTTPException(status_code=400, detail="No document loaded.")

    # Public API uses 1-indexed page numbers; PyMuPDF uses 0-indexed pages.
    page_idx = page_num - 1
    if page_idx < 0 or page_idx >= _state["total_pages"]:
        raise HTTPException(status_code=404, detail="Page number out of range.")

    # Render the PDF page to a raster image. Higher zoom means larger image
    # dimensions and clearer text, at the cost of response size.
    doc = fitz.open(_state["pdf_path"])
    page = doc[page_idx]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)

    if bbox:
        try:
            # Optional highlighting is useful when the frontend wants to show
            # where a retrieved chunk appeared on the page.
            from PIL import Image, ImageDraw
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            draw = ImageDraw.Draw(img)
            b = json.loads(bbox)

            # Docling/PDF coordinates use a bottom-left origin, while PIL image
            # coordinates use a top-left origin, so y values are flipped.
            page_h = page.rect.height
            x0 = b.get("left", 0) * zoom
            x1 = b.get("right", 100) * zoom
            y0 = (page_h - b.get("top", 0)) * zoom
            y1 = (page_h - b.get("bottom", 100)) * zoom
            if y0 > y1:
                y0, y1 = y1, y0
            draw.rectangle([x0, y0, x1, y1], outline="red", width=3)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            png_bytes = buf.getvalue()
        except Exception as e:
            # If highlighting fails, still return the page image instead of
            # failing the endpoint.
            print(f"Bbox highlight error: {e}")
            png_bytes = pix.tobytes("png")
    else:
        png_bytes = pix.tobytes("png")

    doc.close()
    return {"image_base64": base64.b64encode(png_bytes).decode("utf-8")}

@app.get("/sections", tags=["Sections"])
def get_section_definitions():
    """Return the dynamically discovered section definitions."""
    return _state["discovered_sections"]

@app.post("/extract-section", tags=["Sections"])
def extract_section(req: ExtractSectionRequest):
    """Extract and summarize one discovered section using retrieval + LLM."""
    if not _is_loaded():
        raise HTTPException(status_code=400, detail="No document loaded.")

    # Validate the requested key before running extraction so clients get a
    # clear error with the available section keys.
    sections = _state["discovered_sections"]
    if req.section_key not in sections:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown section: {req.section_key}. "
                   f"Available: {list(sections.keys())}",
        )
    try:
        # SectionExtractor retrieves relevant chunks, prompts the LLM, and
        # returns a structured section object.
        section = _state["section_extractor"].extract_section(req.section_key)
        return JSONResponse(content=_sanitize(section.to_dict()))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
   
@app.post("/extract-all", tags=["Sections"])
def extract_all_sections():
    """Extract every discovered section and return them keyed by section_key."""
    if not _is_loaded():
        raise HTTPException(status_code=400, detail="No document loaded.")
    try:
        sections = _state["section_extractor"].extract_all_sections()
        result = {k: _sanitize(s.to_dict()) for k, s in sections.items()}
        return JSONResponse(content=result)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/extracted-sections", tags=["Sections"])
def get_extracted_sections():
    """Return cached extracted sections without recomputing them."""
    if not _is_loaded():
        raise HTTPException(status_code=400, detail="No document loaded.")
    secs = _state["section_extractor"].extracted_sections
    return {k: s.to_dict() for k, s in secs.items()}


@app.post("/chat", tags=["Chat"])
def chat(req: ChatRequest):
    """Answer a user question using retrieved chunks from the loaded document."""
    if not _is_loaded():
        raise HTTPException(status_code=400, detail="No document loaded.")
    try:
        # rag_engine.chat returns both the answer and source chunks so the
        # frontend can display citations/context.
        answer, sources = _state["rag_engine"].chat(req.query)
        return JSONResponse(content={
            "answer": answer,
            "sources": _sanitize(sources),
        })
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
   
@app.get("/chunks", tags=["Chunks"])
def get_chunks(page: Optional[int] = Query(None)):
    """Return processed chunks, optionally filtered to a single page."""
    if not _is_loaded():
        raise HTTPException(status_code=400, detail="No document loaded.")
    chunks = _state["chunks"]
    if page is not None:
        # Page numbers are stored using the original PDF page numbering.
        chunks = [c for c in chunks if c.page_number == page]
    return [c.to_dict() for c in chunks]


# =============================================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.api:app", host="0.0.0.0", port=8000, reload=True)
     
     
