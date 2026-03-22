import os

CHROMA_PERSIST_DIR = "./chroma_db"
COLLECTION_NAME = "mf_prospectus"
EMBEDDING_MODEL = "text-embedding-3-small"
LLM_MODEL = "gpt-4o-mini"
VISION_MODEL = "gpt-4o-mini"
LLM_TEMPERATURE = 0.1 # for low randomness
MAX_TOKENS_PER_CHUNK = 512
TOKENIZER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

RERANK_TOP_K = 10  # Initial retrieval count
FINAL_TOP_K = 5    # After re-ranking

# DOCUMENT VALIDATION SETTINGS

VALIDATION_INITIAL_SCORE = 50
VALIDATION_THRESHOLD = 65
VALIDATION_SCORE_DELTA = 10
VALIDATION_MAX_PAGES = 5

# Sliding-window size: keep last N pages in memory during section scanning
PAGE_MEMORY_WINDOW = 3
