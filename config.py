# This file contains the configuration (paramters, llm model, embedding models) used in the project

# ChromaDB settings
CHROMA_PERSIST_DIR = "./chroma_db"
COLLECTION_NAME = "mf_prospectus_rag"

# Embedding model
EMBEDDING_MODEL = "text-embedding-3-small"

# LLM settings
VLM_MODEL = "gpt-4o-mini"
LLM_TEMPERATURE = 0.1

# Tokenizer settings
MAX_TOKENS_PER_CHUNK = 512
TOKENIZER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Re-Ranking settings
INITIAL_NO_OF_CHUNKS = 10
RE_REANKED_NO_OF_CHUNKS = 5

# Document validation settings
# Vision-based scoring to determine if the uploaded document is a valid Mutual Fund Prospectus document or not
# Start at a particular INITIAL_SCORE, scans first N pages and then for
# Each page adds +DELTA (MF content) or -DELTA (not MF content).
# Valid if final score >= THRESHOLD.

VALIDATION_INITIAL_SCORE = 50
VALIDATION_THRESHOLD = 65
VALIDATION_SCORE_DELTA = 10
VALIDATION_MAX_PAGES = 5

# Sliding-window size: keep last N pages in memory during section scanning
PAGE_MEMORY_WINDOW = 3