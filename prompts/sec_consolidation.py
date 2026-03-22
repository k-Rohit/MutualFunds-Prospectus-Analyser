
# Section Consolidation prompt
SECTION_CONSOLIDATION_PROMPT = """You are an expert financial document analyst.

Below are page-by-page analyses of a mutual fund document.
Consolidate them into a clean, deduplicated section/subsection structure.

PAGE-BY-PAGE FINDINGS:
{page_analyses}

INSTRUCTIONS:
1. Merge sections that span multiple pages into single entries
2. Group related subsections under their parent sections
3. Remove duplicates
4. Create a clean hierarchical structure
5. For each section compile ALL relevant keywords from all pages
6. Generate a section_key (lowercase, underscores, no special chars)
7. Order sections logically as they appear in the document

Respond with EXACTLY this JSON (no markdown fences):
{{
    "sections": [
        {{
            "section_key": "unique_key_like_this",
            "title": "Section Title",
            "description": "What this section covers",
            "subsections": ["Subsection 1", "Subsection 2"],
            "keywords": ["keyword1", "keyword2"],
            "pages": [1, 2]
        }}
    ]
}}"""