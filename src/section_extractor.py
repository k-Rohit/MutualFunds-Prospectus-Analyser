# This script extracts/summarises the section content dynamically from
# the sections extracted using DocumentScanner class

import sys
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from langchain_openai import ChatOpenAI
from pathlib import Path

# Finding the project root and tell Python to also search there for imports.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import *
from rag_engine import RagEngine

@dataclass
class SubsectionContent:
    """Content for a subsection."""
    title: str
    content: str
    chunks: List[Dict] = field(default_factory=list)


@dataclass
class SectionContent:
    """Content for a main section."""
    section_key: str
    title: str
    description: str
    summary: str
    subsections: List[SubsectionContent] = field(default_factory=list)
    all_chunks: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "section_key": self.section_key,
            "title": self.title,
            "description": self.description,
            "summary": self.summary,
            "subsections": [
                {
                    "title": sub.title,
                    "content": sub.content,
                    "chunks": sub.chunks,
                }
                for sub in self.subsections
            ],
            "all_chunks": self.all_chunks,
        }

