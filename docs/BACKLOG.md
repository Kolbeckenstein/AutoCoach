# AutoCoach Feature Backlog

Deferred features and enhancements tracked during design discussions.

---

## RAG v2 Enhancements

Identified during Phase 3 design. The v1 RAG system uses pose-vector-only search
with comments stored as plain-text payload. These enhancements add richer retrieval
strategies for future phases.

### Comment embedding for semantic coaching search
- Embed Reddit comments using sentence-transformers (all-MiniLM-L6-v2, 384-dim)
- Enables text-to-text queries: "find lifts where coaches discussed knee cave"
- Useful for coach-facing research tools, not the v1 user workflow
- Would live in Phase 4 (LLM coaching) as retrieval-augmented generation, where
  the LLM's own analysis generates the text query — not user-facing

### Dimension-weighted pose search
- User says "check for butt wink" → LLM identifies relevant dimension (back_angle
  during bottom phase)
- Reweight the pose vector search to emphasise those specific dimensions
- This is structured query refinement, NOT text embedding search
- Avoids the failure mode of text-embedding search: finding comments *about* butt
  wink attached to lifts that look nothing like the user's

### Hybrid pose + comment reranking
- After pose-similarity retrieval, rerank results by comment quality/relevance
- Weight lifts that received high-quality coaching feedback higher in results
- Requires comment embeddings indexed alongside pose vectors

### Lift-over-time comparison (no retrieval needed)
- "Did I fix my depth?" is a comparison between two of the user's own lifts
- LLM gets both BiomechanicalFeatures and compares directly
- No vector search involved — pure feature diff
