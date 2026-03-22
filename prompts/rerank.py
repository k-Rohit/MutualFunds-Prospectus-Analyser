# Re-rank prompt
RERANK_PROMPT = """Given a query and a list of document chunks, rate how relevant each chunk is to answering the query.

Query: {query}

For each chunk, provide a relevance score from 0 to 10:
- 10: Directly answers the query with specific information
- 7-9: Highly relevant, contains useful related information
- 4-6: Somewhat relevant, may have partial information
- 1-3: Marginally relevant
- 0: Not relevant at all

Chunks to evaluate:
{chunks}

Return your response as a JSON array of objects with 'chunk_id' and 'score' fields.
Example: [{{"chunk_id": 0, "score": 8}}, {{"chunk_id": 1, "score": 3}}, ...]

YOUR RESPONSE (JSON only):"""
