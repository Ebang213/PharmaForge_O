"""
LLM provider service with mock fallback.
"""
from typing import Dict, Any, Optional
from datetime import datetime

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def generate_answer(question: str, context: str) -> str:
    """Generate answer using LLM with context from RAG."""
    if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        return _openai_completion(question, context)
    elif settings.LLM_PROVIDER == "anthropic" and settings.ANTHROPIC_API_KEY:
        return _anthropic_completion(question, context)
    else:
        return _mock_answer(question, context)


def generate_draft_email(question: str, answer: str) -> str:
    """Generate draft email based on Q&A."""
    if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        return _openai_email(question, answer)
    elif settings.LLM_PROVIDER == "anthropic" and settings.ANTHROPIC_API_KEY:
        return _anthropic_email(question, answer)
    else:
        return _mock_email(question, answer)


def generate_rfq_email(rfq_number: str, item_type: str, item_description: str,
                       specifications: dict, quantity: float, quantity_unit: str,
                       delivery_location: str, target_date: datetime,
                       compliance_constraints: dict, vendor_name: str,
                       custom_notes: str = None) -> str:
    """Generate RFQ email draft."""
    if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        return _openai_rfq_email(rfq_number, item_type, item_description, specifications,
                                 quantity, quantity_unit, delivery_location, target_date,
                                 compliance_constraints, vendor_name, custom_notes)
    else:
        return _mock_rfq_email(rfq_number, item_type, item_description, specifications,
                               quantity, quantity_unit, delivery_location, target_date,
                               compliance_constraints, vendor_name, custom_notes)


def generate_war_council_response(question: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate multi-persona War Council response."""
    if settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        return _openai_war_council(question, context)
    else:
        return _mock_war_council(question, context)


# ============= MOCK IMPLEMENTATIONS =============

def _mock_answer(question: str, context: str) -> str:
    """Generate deterministic mock answer."""
    q_lower = question.lower()
    
    if "fda" in q_lower and "guidance" in q_lower:
        return ("Based on the retrieved FDA guidance documents, the FDA recommends following "
                "a risk-based approach to ensure compliance with current Good Manufacturing "
                "Practice (cGMP) requirements. Key considerations include: 1) Establishing "
                "appropriate quality systems, 2) Implementing robust documentation practices, "
                "3) Conducting regular validation studies, and 4) Maintaining traceability "
                "throughout the supply chain.")
    elif "dscsa" in q_lower or "serialization" in q_lower:
        return ("Under DSCSA requirements effective November 2023, trading partners must be "
                "able to verify the product identifier at the package level. This includes: "
                "1) Unique serialization with GTIN, lot number, expiration date, and serial "
                "number, 2) EPCIS-compliant transaction documentation, 3) Verification of "
                "suspicious products within 24 hours, and 4) Interoperable data exchange.")
    elif "recall" in q_lower:
        return ("For product recalls, FDA regulations (21 CFR Part 7) outline a tiered "
                "classification system: Class I for serious health consequences, Class II "
                "for temporary health issues, and Class III for unlikely health impact. "
                "Companies should: 1) Immediately notify FDA, 2) Identify affected lots, "
                "3) Notify trading partners, and 4) Document all recall activities.")
    else:
        if context and len(context) > 100:
            return f"Based on the provided context: {context[:500]}... The relevant regulatory "
            "requirements indicate that compliance should be maintained through documentation, "
            "validation, and risk assessment procedures."
        return ("I found relevant information in your regulatory documents. Please ensure "
                "compliance with applicable FDA regulations and industry standards. For specific "
                "guidance, I recommend consulting the relevant CFR sections or FDA guidance documents.")


def _mock_email(question: str, answer: str) -> str:
    """Generate mock draft email."""
    return f"""Subject: Regulatory Inquiry Follow-up

Dear [Recipient],

I am writing to follow up on our regulatory compliance discussion.

Based on our analysis, {answer[:200]}...

Please let me know if you need any additional clarification or documentation.

Best regards,
[Your Name]
Regulatory Affairs Team"""


def _mock_rfq_email(rfq_number: str, item_type: str, item_description: str,
                    specifications: dict, quantity: float, quantity_unit: str,
                    delivery_location: str, target_date: datetime,
                    compliance_constraints: dict, vendor_name: str,
                    custom_notes: str = None) -> str:
    """Generate mock RFQ email."""
    specs_text = "\n".join([f"  - {k}: {v}" for k, v in (specifications or {}).items()]) or "  - See attached specifications"
    compliance_text = "\n".join([f"  - {k}: {v}" for k, v in (compliance_constraints or {}).items()]) or "  - GMP compliant\n  - FDA-approved facility"
    target_str = target_date.strftime("%B %d, %Y") if target_date else "To be discussed"
    
    return f"""Dear {vendor_name} Team,

We are pleased to invite you to submit a quotation for the following Request for Quote:

RFQ Number: {rfq_number}

ITEM DETAILS:
Item Type: {item_type}
Description: {item_description}

Specifications:
{specs_text}

QUANTITY REQUIREMENTS:
Quantity: {quantity} {quantity_unit or 'units'}
Delivery Location: {delivery_location or 'To be confirmed'}
Target Delivery Date: {target_str}

COMPLIANCE REQUIREMENTS:
{compliance_text}

{f"Additional Notes: {custom_notes}" if custom_notes else ""}

Please provide your quotation including:
1. Unit price and total price
2. Minimum order quantity (MOQ)
3. Lead time from order confirmation
4. Incoterms
5. Payment terms
6. Quote validity period
7. Certificate of Analysis (CoA) template
8. Relevant compliance certifications

We kindly request your response by [RESPONSE_DEADLINE].

If you have any questions, please do not hesitate to contact us.

Best regards,
Procurement Team"""


def _mock_war_council(question: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Generate mock multi-persona War Council response."""
    vendors = context.get("vendors", [])
    vendor_names = [v.get("name", "Unknown") for v in vendors]
    
    return {
        "regulatory": {
            "response": f"From a regulatory perspective, this situation requires careful evaluation of FDA compliance "
                       f"requirements. Key considerations include 21 CFR Part 211 for cGMP and ensuring all documentation "
                       f"is properly maintained. {'Vendors ' + ', '.join(vendor_names) + ' should be assessed for their compliance history.' if vendor_names else ''}",
            "key_points": ["FDA compliance documentation required", "cGMP adherence critical", "Risk assessment needed"],
            "risk_level": "medium",
            "actions": ["Review compliance documentation", "Conduct risk assessment", "Update regulatory filing if needed"],
        },
        "supply_chain": {
            "response": f"Supply chain analysis indicates potential risks in continuity and lead times. "
                       f"{'Current vendors ' + ', '.join(vendor_names) + ' show varying risk profiles.' if vendor_names else ''} "
                       f"Recommend diversifying supply base and establishing buffer inventory.",
            "key_points": ["Supply continuity risk exists", "Lead time variability", "Inventory buffer recommended"],
            "risk_level": "high" if any(v.get("risk_level") == "high" for v in vendors) else "medium",
            "actions": ["Identify backup suppliers", "Increase safety stock", "Negotiate expedited shipping terms"],
        },
        "legal": {
            "response": "Legal review suggests ensuring all contractual obligations are clearly defined. "
                       "Force majeure clauses should be reviewed, and liability provisions must be adequate. "
                       "Recommend consulting with legal counsel before making significant supply chain changes.",
            "key_points": ["Contract review required", "Liability assessment needed", "IP protection considerations"],
            "risk_level": "low",
            "actions": ["Review supply agreements", "Update force majeure clauses", "Ensure adequate insurance"],
        },
        "synthesis": f"The War Council recommends a balanced approach addressing regulatory compliance, supply chain "
                    f"resilience, and legal protection. Immediate priorities should focus on risk mitigation while "
                    f"maintaining operational continuity.",
        "overall_risk": "medium",
        "priority_actions": [
            "Conduct immediate risk assessment of current suppliers",
            "Review and update compliance documentation",
            "Identify and qualify backup suppliers",
            "Review contractual terms with legal",
        ],
        "references": {"vendors": vendor_names, "context": context.get("notes")},
    }


# ============= REAL LLM IMPLEMENTATIONS =============

def _openai_completion(question: str, context: str) -> str:
    """OpenAI completion for Q&A."""
    try:
        import openai
        openai.api_key = settings.OPENAI_API_KEY
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a pharmaceutical regulatory expert. Answer questions based on the provided context."},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ],
            max_tokens=1000,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return _mock_answer(question, context)


def _openai_email(question: str, answer: str) -> str:
    """OpenAI email generation."""
    try:
        import openai
        openai.api_key = settings.OPENAI_API_KEY
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Generate a professional email based on the Q&A."},
                {"role": "user", "content": f"Question: {question}\nAnswer: {answer}\n\nGenerate a draft email."},
            ],
            max_tokens=500,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return _mock_email(question, answer)


def _anthropic_completion(question: str, context: str) -> str:
    """Anthropic completion for Q&A."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        
        response = client.messages.create(
            model="claude-3-sonnet-20240229",
            max_tokens=1000,
            messages=[{"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}],
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"Anthropic error: {e}")
        return _mock_answer(question, context)


def _anthropic_email(question: str, answer: str) -> str:
    """Anthropic email generation."""
    return _mock_email(question, answer)


def _openai_rfq_email(*args, **kwargs) -> str:
    """OpenAI RFQ email - falls back to mock for now."""
    return _mock_rfq_email(*args, **kwargs)


def _openai_war_council(question: str, context: Dict) -> Dict:
    """OpenAI War Council - falls back to mock for now."""
    return _mock_war_council(question, context)
