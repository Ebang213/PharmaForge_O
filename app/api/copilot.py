"""
Regulatory Copilot API routes - RAG-powered Q&A.
"""
from typing import List, Optional
from datetime import datetime
import hashlib
import os
import time

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.db.models import (
    Document, DocumentChunk, CopilotSession, CopilotMessage, AuditLog
)
from app.core.rbac import require_operator, get_current_user_context
from app.core.config import settings
from app.services.rag_ingest import process_document_async
from app.services.rag_query import query_documents
from app.services.llm_provider import generate_answer, generate_draft_email

router = APIRouter(prefix="/api/copilot", tags=["Copilot"])


# ============= SCHEMAS =============

class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_size: int
    doc_type: Optional[str]
    title: Optional[str]
    is_processed: bool
    chunk_count: int
    created_at: datetime
    processed_at: Optional[datetime]
    processing_error: Optional[str]
    
    class Config:
        orm_mode = True


class QueryRequest(BaseModel):
    question: str
    session_id: Optional[int] = None
    include_draft_email: bool = True


class Citation(BaseModel):
    doc_name: str
    chunk_id: int
    page: Optional[int]
    section: Optional[str]
    content_preview: str
    confidence: float


class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]
    draft_email: Optional[str]
    session_id: int
    message_id: int
    latency_ms: int


class SessionResponse(BaseModel):
    id: int
    title: Optional[str]
    created_at: datetime
    message_count: int
    
    class Config:
        orm_mode = True


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    citations: Optional[List[dict]]
    draft_email: Optional[str]
    created_at: datetime
    
    class Config:
        orm_mode = True


# ============= ROUTES =============

@router.get("/documents", response_model=List[DocumentResponse])
async def list_documents(
    doc_type: Optional[str] = Query(None, description="Filter by document type"),
    processed_only: bool = Query(False, description="Show only processed documents"),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """List uploaded documents."""
    query = db.query(Document).filter(
        Document.organization_id == user_context["org_id"]
    )
    
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    
    if processed_only:
        query = query.filter(Document.is_processed == True)
    
    documents = query.order_by(desc(Document.created_at)).offset(offset).limit(limit).all()
    
    return [
        DocumentResponse(
            id=d.id,
            filename=d.filename,
            file_size=d.file_size or 0,
            doc_type=d.doc_type,
            title=d.title,
            is_processed=d.is_processed,
            chunk_count=d.chunk_count or 0,
            created_at=d.created_at,
            processed_at=d.processed_at,
            processing_error=d.processing_error,
        )
        for d in documents
    ]


@router.post("/documents/upload", response_model=DocumentResponse)
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_type: Optional[str] = None,
    title: Optional[str] = None,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Upload a document for RAG processing."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    ext = file.filename.lower().split('.')[-1]
    if ext not in ['pdf', 'txt', 'md', 'docx']:
        raise HTTPException(status_code=400, detail="File must be PDF, TXT, MD, or DOCX")
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    if file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large")
    
    # Calculate hash
    file_hash = hashlib.sha256(content).hexdigest()
    
    # Save file
    upload_dir = os.path.join(settings.UPLOAD_DIR, "documents")
    os.makedirs(upload_dir, exist_ok=True)
    
    file_path = os.path.join(upload_dir, f"{file_hash}_{file.filename}")
    with open(file_path, 'wb') as f:
        f.write(content)
    
    # Create document record
    document = Document(
        organization_id=user_context["org_id"],
        uploaded_by=int(user_context["sub"]),
        filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        file_hash=file_hash,
        content_type=ext,
        doc_type=doc_type,
        title=title or file.filename,
    )
    db.add(document)
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="upload_document",
        entity_type="document",
        details={"filename": file.filename, "doc_type": doc_type},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(document)
    
    # Queue background processing
    background_tasks.add_task(process_document_async, document.id)
    
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        file_size=document.file_size or 0,
        doc_type=document.doc_type,
        title=document.title,
        is_processed=document.is_processed,
        chunk_count=document.chunk_count or 0,
        created_at=document.created_at,
        processed_at=document.processed_at,
        processing_error=document.processing_error,
    )


@router.post("/query", response_model=QueryResponse)
async def query_copilot(
    request: Request,
    query_data: QueryRequest,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Ask a question to the Regulatory Copilot."""
    start_time = time.time()
    org_id = user_context["org_id"]
    user_id = int(user_context["sub"])
    
    # Get or create session
    if query_data.session_id:
        session = db.query(CopilotSession).filter(
            CopilotSession.id == query_data.session_id,
            CopilotSession.organization_id == org_id
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session = CopilotSession(
            organization_id=org_id,
            user_id=user_id,
            title=query_data.question[:100],
        )
        db.add(session)
        db.flush()
    
    # Store user message
    user_message = CopilotMessage(
        session_id=session.id,
        role="user",
        content=query_data.question,
    )
    db.add(user_message)
    db.flush()
    
    # Query vector DB for relevant chunks
    relevant_chunks = query_documents(db, org_id, query_data.question, top_k=5)
    
    # Build context from chunks
    context_parts = []
    citations = []
    for idx, chunk in enumerate(relevant_chunks):
        context_parts.append(f"[Source {idx + 1}]: {chunk['content']}")
        citations.append(Citation(
            doc_name=chunk["doc_name"],
            chunk_id=chunk["chunk_id"],
            page=chunk.get("page"),
            section=chunk.get("section"),
            content_preview=chunk["content"][:200],
            confidence=chunk["score"],
        ))
    
    context = "\n\n".join(context_parts)
    
    # Generate answer using LLM
    answer = generate_answer(query_data.question, context)
    
    # Generate draft email if requested
    draft_email = None
    if query_data.include_draft_email:
        draft_email = generate_draft_email(query_data.question, answer)
    
    latency_ms = int((time.time() - start_time) * 1000)
    
    # Store assistant message
    assistant_message = CopilotMessage(
        session_id=session.id,
        role="assistant",
        content=answer,
        citations=[c.dict() for c in citations],
        draft_email=draft_email,
        latency_ms=latency_ms,
    )
    db.add(assistant_message)
    
    # Audit log
    audit_log = AuditLog(
        user_id=user_id,
        organization_id=org_id,
        action="copilot_query",
        entity_type="copilot_session",
        entity_id=session.id,
        details={
            "question": query_data.question[:200],
            "citations_count": len(citations),
            "latency_ms": latency_ms,
        },
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    
    return QueryResponse(
        answer=answer,
        citations=citations,
        draft_email=draft_email,
        session_id=session.id,
        message_id=assistant_message.id,
        latency_ms=latency_ms,
    )


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """List copilot sessions for current user."""
    sessions = db.query(CopilotSession).filter(
        CopilotSession.organization_id == user_context["org_id"],
        CopilotSession.user_id == int(user_context["sub"])
    ).order_by(desc(CopilotSession.created_at)).offset(offset).limit(limit).all()
    
    return [
        SessionResponse(
            id=s.id,
            title=s.title,
            created_at=s.created_at,
            message_count=len(s.messages) if s.messages else 0,
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
async def get_session_messages(
    session_id: int,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Get messages in a copilot session."""
    session = db.query(CopilotSession).filter(
        CopilotSession.id == session_id,
        CopilotSession.organization_id == user_context["org_id"]
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return [
        MessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            citations=m.citations,
            draft_email=m.draft_email,
            created_at=m.created_at,
        )
        for m in session.messages
    ]


@router.get("/health")
async def copilot_health(
    db: Session = Depends(get_db)
):
    """
    Copilot module health check.
    Returns status and configuration info.
    """
    from app.core.config import settings
    
    # Get document and session counts
    doc_count = db.query(Document).count()
    session_count = db.query(CopilotSession).count()
    
    return {
        "status": "healthy",
        "module": "copilot",
        "llm_provider": settings.LLM_PROVIDER,
        "mock_mode": settings.LLM_PROVIDER == "mock",
        "document_count": doc_count,
        "session_count": session_count,
        "message": "Mock responses enabled" if settings.LLM_PROVIDER == "mock" else "LLM integration active"
    }


@router.post("/chat")
async def chat_copilot(
    request: Request,
    data: dict,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """
    Simple chat endpoint (alias for query with message format).
    Returns a response to a user message.
    """
    message = data.get("message", "")
    context = data.get("context", {})
    
    # Use query logic with message
    query_data = QueryRequest(
        question=message,
        session_id=None,
        include_draft_email=False
    )
    
    # Simplified response for chat
    from app.services.llm_provider import generate_answer
    answer = generate_answer(message, str(context))
    
    return {
        "message": answer,
        "mode": settings.LLM_PROVIDER,
    }

