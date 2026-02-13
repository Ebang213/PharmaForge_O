"""
RAG query service for document retrieval.
"""
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk

logger = get_logger(__name__)


def query_documents(db: Session, org_id: int, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """Query documents using vector similarity search."""
    try:
        query_embedding = generate_query_embedding(query)
        results = search_vector_db(query_embedding, org_id, top_k)
        if results:
            return results
    except Exception as e:
        logger.warning(f"Vector search failed: {e}")
    
    return keyword_search(db, org_id, query, top_k)


def generate_query_embedding(query: str) -> List[float]:
    """Generate embedding for query text."""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(settings.EMBEDDING_MODEL)
        return model.encode(query).tolist()
    except ImportError:
        import hashlib
        hash_bytes = hashlib.sha384(query.encode()).digest()
        return [float(b) / 255.0 for b in hash_bytes]


def search_vector_db(query_embedding: List[float], org_id: int, top_k: int) -> List[Dict]:
    """Search Qdrant for similar vectors."""
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
        results = client.search(collection_name=settings.QDRANT_COLLECTION, query_vector=query_embedding, limit=top_k)
        formatted = []
        for hit in results:
            payload = hit.payload or {}
            formatted.append({
                "chunk_id": hit.id,
                "doc_id": payload.get("doc_id"),
                "doc_name": payload.get("doc_name", "Unknown"),
                "content": get_chunk_content(hit.id),
                "page": payload.get("page"),
                "section": payload.get("section"),
                "score": hit.score,
            })
        return formatted
    except Exception as e:
        logger.warning(f"Qdrant search failed: {e}")
        return []


def get_chunk_content(chunk_id: int) -> str:
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
        return chunk.content if chunk else ""
    finally:
        db.close()


def keyword_search(db: Session, org_id: int, query: str, top_k: int) -> List[Dict]:
    """Fallback keyword search."""
    documents = db.query(Document).filter(Document.organization_id == org_id, Document.is_processed == True).all()
    doc_ids = [d.id for d in documents]
    if not doc_ids:
        return []
    
    keywords = query.lower().split()
    chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id.in_(doc_ids)).all()
    scored = []
    for chunk in chunks:
        content_lower = chunk.content.lower()
        score = sum(1 for kw in keywords if kw in content_lower)
        if score > 0:
            doc = db.query(Document).filter(Document.id == chunk.document_id).first()
            scored.append({
                "chunk_id": chunk.id, "doc_id": chunk.document_id,
                "doc_name": doc.filename if doc else "Unknown", "content": chunk.content,
                "page": chunk.page_number, "section": chunk.section_title, "score": score / len(keywords),
            })
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
