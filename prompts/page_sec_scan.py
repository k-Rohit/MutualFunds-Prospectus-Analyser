PAGE_SECTION_SCAN_PROMPT = """You are an expert financial document analyst.

Analyze this PDF page image and identify all **sections and subsections**
visible on the page.

{memory_context}

INSTRUCTIONS:
1. Identify every distinct section / heading / subsection on this page
2. For each section determine:
   - The title as it appears on the page
   - A brief description of what information it contains
   - Key topics, terms, or data points (keywords for search)
   - Any subsection headings nested under it
   - Whether it is a continuation from a previous page
3. Capture tables, charts, headers, footers, disclaimers
4. If a section from a previous page continues here, note that

Respond with EXACTLY this JSON (no markdown fences):
{{
    "page_number": {page_num},
    "sections_found": [
        {{
            "title": "Section title as it appears",
            "description": "What information this section contains",
            "keywords": ["keyword1", "keyword2", "keyword3"],
            "subsections": ["Sub-heading 1", "Sub-heading 2"],
            "is_continuation": false,
            "content_summary": "One-line summary of this section on this page"
        }}
    ],
    "page_summary": "One-line summary of what this entire page covers"
}}"""