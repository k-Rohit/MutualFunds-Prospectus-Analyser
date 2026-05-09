# Document Scanner - Vision-based validation & dynamic section discovery
# This file validates whether the document is a valid mutual fund doc or not.
# Then it tries to discover/ find out the sections and the subsections the document contains
# and then consolidates the section using the consolidation prompt.


import json
import fitz  
import base64
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
     sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()
from config import *
from prompts import *


# class for memory
class SlidingWindowMemory:
     """
     SlidingWindowMemory keeps the last few page-analysis conversations so the model can understand continuity across pages.
     """
     
     def __init__(self, window_size: int = 3):
          # variable_name: expected_type = value
          self.messages: List[HumanMessage | AIMessage] = []
          self.window_size: int = window_size
          
     def add_exchange(self, user_input: str, ai_output: str):
          """Record one page-analysis exchange."""
          self.messages.append(HumanMessage(content=user_input))
          self.messages.append(AIMessage(content=ai_output))
     
     def get_context_string(self) -> str:
        """Return a text block of the last *window_size* AI responses."""
        recent = self.messages[-(self.window_size * 2):]
        if not recent:
            return ""
        parts = []
        for msg in recent:
            if isinstance(msg, AIMessage):
                parts.append(msg.content)
        if not parts:
            return ""
        return "CONTEXT FROM PREVIOUS PAGES:\n" + "\n".join(parts)

     def get_messages(self):
          """Return the raw LangChain messages in the current window."""
          return self.messages[-(self.window_size * 2):]
     
# class for scannig the page - check validity and discover sections
class DocumentScanner:
     """
     This class scans a PDF like a human analyst would:
     a. “Is this really a mutual fund prospectus?”
     b. “What sections does this document contain?”
     c. “Which pages contain each section?”
     d. “What subsections and keywords belong to each section?”
     e. “Merge repeated/continued sections into one clean structure.”
     """
     
     def __init__(self):
          # Vision LLM for page images.
          self.vision_llm = ChatOpenAI(
               model=VLM_MODEL,
               temperature=LLM_TEMPERATURE,
               max_tokens=2000,
               openai_api_key=OPENAI_API_KEY
          )

          # Text LLM for consolidation, no images needed.
          self.text_llm = ChatOpenAI(
               model=LLM_MODEL,
               temperature=LLM_TEMPERATURE,
               max_tokens=4000,
               openai_api_key=OPENAI_API_KEY
          )

          self.discovered_sections: Dict = {}
          self.validation_result: Dict = {}
     
     @staticmethod
     def _render_page_to_image(pdf_path: str, page_idx: int,
                               zoom: float = 1.5):
          """
          Converts pdf to image

          Args:
              pdf_path (str): path of the pdf
              page_idx (int): index of the page
              zoom (float, optional): Defaults to 1.5.

          """
          
          doc = fitz.open(pdf_path)
          page = doc[page_idx]
          mat = fitz.Matrix(zoom, zoom)
          pix = page.get_pixmap(matrix=mat)
          png_bytes = pix.tobytes("png")
          doc.close()
          return base64.b64encode(png_bytes).decode("utf-8")
     
     @staticmethod
     def _get_page_count(pdf_path: str) -> int:
          """
          Counts the number of the pages in the pdf
          """
          doc = fitz.open(pdf_path)
          count = len(doc)
          doc.close()
          return count
     
     def _call_vision(self, prompt_text: str, image_base64: str) -> str:
        """Send text + image to the vision model and return the response."""
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt_text},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_base64}"
                    },
                },
            ]
        )
        response = self.vision_llm.invoke([message])
        return response.content
   
   
     @staticmethod
     def _parse_json_response(text: str) -> Dict:
          """
          Extract and parse JSON content from an LLM response.

          This method handles responses where JSON may be wrapped inside
          Markdown code fences such as ```json ... ``` or generic ``` ... ```.

          Args:
               text (str): Raw response text returned by the LLM.

          Returns:
               Dict: Parsed JSON as a Python dictionary.
               Returns an empty dictionary if parsing fails.

          Example:
               Input:
                    ```json
                    {
                         "name": "Rohit"
                    }
                    ```

               Output:
                    {"name": "Rohit"}
          """

          text = text.strip()
          if "```json" in text:
               text = text.split("```json")[1].split("```")[0]
          elif "```" in text:
               text = text.split("```")[1].split("```")[0]
          try:
               return json.loads(text.strip())
          except json.JSONDecodeError:
               return {}
          
     def validate_document(self, pdf_path: str) -> Tuple[bool, int, str]:
          
          """
          This function validates whether a pdf is a mutual fund document or not.
          
          Scans the first (VALIDATION_MAX_PAGES) pages with the vision model.
          Starts at VALIDATION_INITIAL_SCORE = 50.
          After scanning each page it adds a number (DELTA=10) +DELTA (if MF content) or -DELTA (if Not MF content)
          according the content. The document is **valid** when the final score ≥ *VALIDATION_THRESHOLD*.
          
          Returns
          -------
          (is_valid, final_score, summary_reason)
          
          """
          total_pages = self._get_page_count(pdf_path)
          pages_to_scan = min(total_pages,VALIDATION_MAX_PAGES)
          
          score = VALIDATION_INITIAL_SCORE
          reasons: List[str] = []
          
          print(f"Validating document ({pages_to_scan} pages to scan) …")
          print(f"  Initial score: {score}")
          
          for page_idx in range(pages_to_scan):
               try:
                    image_b64 = self._render_page_to_image(pdf_path,page_idx)
                    response_text = self._call_vision(DOCUMENT_VALIDATION_PROMPT,image_b64)
                    result = self._parse_json_response(response_text)
                    
                    is_mf = result.get("is_mf_document",False)
                    reason = result.get("reason", "No reason provided")
                    
                    if is_mf:
                         score += VALIDATION_SCORE_DELTA
                         print(
                         f"  Page {page_idx + 1}: "
                         f"+{VALIDATION_SCORE_DELTA} (MF content) → {score}  "
                         f"| {reason}"
                    )
                    else:
                         score -= VALIDATION_SCORE_DELTA
                         print(
                         f"  Page {page_idx + 1}: "
                         f"-{VALIDATION_SCORE_DELTA} (not MF) → {score}  "
                         f"| {reason}"
                    )
                    reasons.append(f"Page {page_idx + 1}: {reason}")
                    
               except Exception as e:
                    print(f"  Page {page_idx + 1}: Error — {e}")
                    reasons.append(f"Page {page_idx + 1}: Error — {e}")
          
          is_valid = score >= VALIDATION_THRESHOLD
          summary = f"Score: {score}/100. " + " | ".join(reasons[:3])
          
          self.validation_result = {
          "is_valid": is_valid,
          "score": score,
          "threshold": VALIDATION_THRESHOLD,
          "pages_scanned": pages_to_scan,
          "reasons": reasons,
          "summary": summary,
     }

          tag = "VALID ✓" if is_valid else "REJECTED ✗"
          print(
               f"\nValidation: {tag}  "
               f"(score {score}, threshold {VALIDATION_THRESHOLD})"
          )
          return is_valid, score, summary
     
     def discover_sections(self, pdf_path: str) -> Dict:
          """
          This function scans each page of the document to discover the section
          and the subsections in the pages.
          
          Uses a ``SlidingWindowMemory`` (LangChain HumanMessage / AIMessage)
          of the last *PAGE_MEMORY_WINDOW* pages so the model can see
          continuity across page boundaries.
          
          Returns
          -------
          dict  –  ``{section_key: {title, description, subsections, keywords, pages}}``
                    (same shape the rest of the pipeline expects)
          """
          total_pages = self._get_page_count(pdf_path)
          memory = SlidingWindowMemory(window_size=PAGE_MEMORY_WINDOW)
          page_analysis: List[Dict] = []
          
          print(f"\nDiscovering sections across {total_pages} pages …")
          
          for page_idx in range(total_pages):
               page_num = page_idx + 1
               print(f"  Scanning page {page_num}/{total_pages} …")
               
               try:
                    # Build prompt with memory context
                    memory_context = memory.get_context_string()
                    prompt = PAGE_SECTION_SCAN_PROMPT.format(
                         memory_context=memory_context,
                         page_num = page_num
                    )
                    
                    image_b64 = self._render_page_to_image(pdf_path,page_idx)
                    response_text = self._call_vision(prompt,image_b64)
                    result = self._parse_json_response(response_text)
                    
                    if result:
                         page_analysis.append(result)
                         page_summary = result.get(
                              "page_summary", f"Page {page_num} analyzed but no summary generated"
                         )
                         section_titles = [
                              s.get("title", "") for s in result.get("sections_found", [])
                         ]
                         memory.add_exchange(
                              user_input=f"Scan page {page_num}",
                              ai_output=(
                                   f"Page {page_num}: {page_summary}. "
                                   f"Sections: {', '.join(section_titles)}"
                              )
                         )
                         print(
                              f"Found {len(section_titles)} sections: "
                              f"{section_titles}"
                         )
                    else:
                         print(f"No structured response for page {page_num}")
               
               except Exception as e:
                    print(f"Can't process and discover sections on {page_num} : error {e}")
               
                       # Consolidate page-level findings into clean section tree
          print("\nConsolidating sections …")
          self.discovered_sections = self._consolidate_sections(page_analysis)

          print(f"Discovered {len(self.discovered_sections)} sections:")
          for key, sec in self.discovered_sections.items():
               n_sub = len(sec.get("subsections", []))
               n_kw = len(sec.get("keywords", []))
               print(f" {sec['title']}  ({n_sub} subsections, {n_kw} keywords)")

          return self.discovered_sections
     
     def _consolidate_sections(self,page_analysis: List[Dict]) -> Dict:
          
          """
          This functions takes many page-level section detections 
          and uses the text LLM to merge duplicates, c
          onnect continuation pages, combine keywords/subsections, 
          and return one organized section map for the whole PDF.
          """
          
          analysis_text = ""
          for analysis in page_analysis:
               page_num = analysis.get("page_number", "?")
               analysis_text += f"\n--- Page {page_num} ---\n"
               analysis_text += (
                    f"Summary: {analysis.get('page_summary', 'N/A')}\n"
               )
               for sec in analysis.get("sections_found", []):
                    analysis_text += f"  Section: {sec.get('title', 'Unknown')}\n"
                    analysis_text += (
                         f"    Description: {sec.get('description', '')}\n"
                    )
                    kw = sec.get("keywords", [])
                    analysis_text += f"Keywords: {', '.join(kw)}\n"
                    subs = sec.get("subsections", [])
                    if subs:
                         analysis_text += f"Subsections: {', '.join(subs)}\n"
                    analysis_text += (
                         f"    Continuation: {sec.get('is_continuation', False)}\n"
                    )
                    analysis_text += (
                         f"    Content: {sec.get('content_summary', '')}\n"
                    )

          prompt = SECTION_CONSOLIDATION_PROMPT.format(
               page_analyses=analysis_text
          )
          response = self.text_llm.invoke(prompt)
          result = self._parse_json_response(response.content)

          # Convert the list into a keyed dict
          sections_dict: Dict = {}
          for idx, sec in enumerate(result.get("sections", [])):
               key = sec.get("section_key", f"section_{idx}")
               sections_dict[key] = {
                    "title": sec.get("title", f"Section {idx + 1}"),
                    "description": sec.get("description", ""),
                    "subsections": sec.get("subsections", []),
                    "keywords": sec.get("keywords", []),
                    "pages": sec.get("pages", []),
               }

          return sections_dict

               
                         
          
                         
                    

          
          
