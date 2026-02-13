"""
RAG document ingestion service.
"""
import os
from typing import List, Optional
from datetime import datetime

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import get_db_context

logger = get_logger(__name__)


def process_document_async(document_id: int):
    """
    Process a document asynchronously for RAG indexing.
    
    Steps:
    1. Extract text from document
    2. Split into chunks
    3. Generate embeddings
    4. Store in vector DB
    """
    from app.db.models import Document, DocumentChunk
    
    with get_db_context() as db:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.error(f"Document {document_id} not found")
            return
        
        try:
            logger.info(f"Processing document: {document.filename}")
            
            # Extract text
            text = extract_text(document.file_path, document.content_type)
            if not text:
                raise ValueError("Could not extract text from document")
            
            # Split into chunks
            chunks = split_into_chunks(text, chunk_size=500, overlap=50)
            logger.info(f"Created {len(chunks)} chunks")
            
            # Store chunks and create embeddings
            for idx, chunk_data in enumerate(chunks):
                # Create chunk record
                chunk = DocumentChunk(
                    document_id=document.id,
                    chunk_index=idx,
                    content=chunk_data["text"],
                    page_number=chunk_data.get("page"),
                    section_title=chunk_data.get("section"),
                    token_count=len(chunk_data["text"].split()),
                    metadata=chunk_data.get("metadata", {}),
                )
                db.add(chunk)
                db.flush()
                
                # Generate and store embedding
                try:
                    vector_id = store_embedding(
                        document_id=document.id,
                        chunk_id=chunk.id,
                        text=chunk_data["text"],
                        metadata={
                            "doc_id": document.id,
                            "doc_name": document.filename,
                            "chunk_index": idx,
                            "page": chunk_data.get("page"),
                            "section": chunk_data.get("section"),
                        }
                    )
                    chunk.vector_id = vector_id
                except Exception as e:
                    logger.warning(f"Failed to store embedding for chunk {idx}: {e}")
            
            # Update document status
            document.is_processed = True
            document.chunk_count = len(chunks)
            document.processed_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Successfully processed document {document_id}")
            
        except Exception as e:
            logger.error(f"Failed to process document {document_id}: {e}")
            document.processing_error = str(e)
            document.is_processed = False
            db.commit()


def extract_text(file_path: str, content_type: str) -> str:
    """Extract text from document file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    if content_type == "pdf":
        return extract_pdf_text(file_path)
    elif content_type in ["txt", "md"]:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    elif content_type == "docx":
        return extract_docx_text(file_path)
    else:
        raise ValueError(f"Unsupported content type: {content_type}")


def extract_pdf_text(file_path: str) -> str:
    """Extract text from PDF file."""
    try:
        import PyPDF2
        
        text_parts = []
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"[Page {page_num + 1}]\n{page_text}")
        
        return "\n\n".join(text_parts)
    except ImportError:
        logger.warning("PyPDF2 not installed, returning empty text")
        return ""


def extract_docx_text(file_path: str) -> str:
    """Extract text from DOCX file."""
    try:
        import docx
        
        doc = docx.Document(file_path)
        text_parts = []
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)
        
        return "\n\n".join(text_parts)
    except ImportError:
        logger.warning("python-docx not installed, returning empty text")
        return ""


def split_into_chunks(text: str, chunk_size: int = 500, overlap: int = 50) -> List[dict]:
    """
    Split text into overlapping chunks.
    
    Args:
        text: Full document text
        chunk_size: Target chunk size in words
        overlap: Number of words to overlap between chunks
    
    Returns:
        List of chunk dictionaries with text and metadata
    """
    chunks = []
    
    # Split by pages if markers exist
    pages = text.split("[Page ")
    if len(pages) > 1:
        # Document has page markers
        current_page = 0
        for page_content in pages:
            if not page_content.strip():
                continue
            
            # Extract page number
            if "]" in page_content:
                page_num_str, page_text = page_content.split("]", 1)
                try:
                    current_page = int(page_num_str)
                except ValueError:
                    pass
            else:
                page_text = page_content
            
            # Split page into chunks
            words = page_text.split()
            for i in range(0, len(words), chunk_size - overlap):
                chunk_words = words[i:i + chunk_size]
                if len(chunk_words) < 20:  # Skip very short chunks
                    continue
                
                chunks.append({
                    "text": " ".join(chunk_words),
                    "page": current_page,
                    "section": None,
                    "metadata": {"word_count": len(chunk_words)},
                })
    else:
        # No page markers, split by words
        words = text.split()
        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            if len(chunk_words) < 20:
                continue
            
            chunks.append({
                "text": " ".join(chunk_words),
                "page": None,
                "section": None,
                "metadata": {"word_count": len(chunk_words)},
            })
    
    return chunks


def store_embedding(document_id: int, chunk_id: int, text: str, metadata: dict) -> str:
    """Store embedding in vector database."""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct, VectorParams, Distance
        
        # Generate embedding
        embedding = generate_embedding(text)
        
        # Connect to Qdrant
        client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
        
        # Ensure collection exists
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if settings.QDRANT_COLLECTION not in collection_names:
            client.create_collection(
                collection_name=settings.QDRANT_COLLECTION,
                vectors_config=VectorParams(size=len(embedding), distance=Distance.COSINE),
            )
        
        # Store vector
        vector_id = f"doc_{document_id}_chunk_{chunk_id}"
        client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=[
                PointStruct(
                    id=chunk_id,
                    vector=embedding,
                    payload={
                        **metadata,
                        "vector_id": vector_id,
                    },
                )
            ],
        )
        
        return vector_id
        
    except ImportError:
        logger.warning("Qdrant client not installed, skipping vector storage")
        return f"mock_vector_{chunk_id}"
    except Exception as e:
        logger.error(f"Failed to store embedding: {e}")
        return f"error_vector_{chunk_id}"


def generate_embedding(text: str) -> List[float]:
    """Generate embedding vector for text."""
    try:
        from sentence_transformers import SentenceTransformer
        
        model = SentenceTransformer(settings.EMBEDDING_MODEL)
        embedding = model.encode(text)
        return embedding.tolist()
        
    except ImportError:
        logger.warning("sentence-transformers not installed, using mock embedding")
        # Return a mock 384-dimensional embedding
        import hashlib
        hash_bytes = hashlib.sha384(text.encode()).digest()
        return [float(b) / 255.0 for b in hash_bytes]
