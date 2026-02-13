import PyPDF2
import io
import re
from typing import Tuple, Optional, Dict, Any
from app.db.models import RiskLevel

def extract_text_from_pdf(content: bytes) -> str:
    """
    Extract text from PDF bytes.
    Returns empty string if extraction fails.
    """
    try:
        pdf_file = io.BytesIO(content)
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        print(f"PDF extraction error: {str(e)}")
        return ""

def analyze_document_content(text: str, vendors: list) -> Dict[str, Any]:
    """
    Rule-based analysis of document text.
    Returns detected type, severity, and matched vendor.
    """
    text_upper = text.upper()
    
    # Simple rule-based alerting
    severity = RiskLevel.LOW
    doc_type = "GENERAL"
    
    if "RECALL" in text_upper:
        severity = RiskLevel.CRITICAL
        doc_type = "RECALL NOTICE"
    elif "WARNING LETTER" in text_upper:
        severity = RiskLevel.HIGH
        doc_type = "WARNING LETTER"
    elif "483" in text_upper:
        severity = RiskLevel.MEDIUM
        doc_type = "FORM 483"
    
    # Vendor matching heuristic
    matched_vendor_id = None
    for vendor in vendors:
        # Check if vendor name exists in text
        if vendor.name.upper() in text_upper:
            matched_vendor_id = vendor.id
            break
            
    return {
        "doc_type": doc_type,
        "severity": severity,
        "matched_vendor_id": matched_vendor_id,
        "title": f"New {doc_type} detected",
        "description": f"Evidence analysis detected a {doc_type} with {severity.value} severity."
    }
