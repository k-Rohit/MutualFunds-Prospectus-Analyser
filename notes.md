# Why Convert PDF Pages to Images for Section/Subsection Discovery in RAG?

## Core Reason
For mutual fund prospectus RAG systems, PDFs are sometimes converted to images and passed to a Vision LLM because the main goal is accurate **section and subsection discovery**, not just text extraction. Traditional PDF parsers can lose important structural cues like heading hierarchy, bold fonts, indentation, multi-column reading order, tables, and spacing, which are critical for correctly identifying sections such as Risk Factors or Expense Ratio. A Vision LLM sees the document visually like a human and can better infer document structure from layout cues, making section-wise summarization more reliable, though this approach is slower and more expensive than text-based parsing.


# Uses of Docling classes used
## 1. DocumentConverter
It takes a PDF/DOCX/etc and converts it into a structured Docling document object.

## 2. HybridChunker
Used to split the parsed document into intelligent chunks for RAG.

## 3. TableItem
Represents a detected table inside the parsed document.