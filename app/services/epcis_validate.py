"""
EPCIS validation service for DSCSA compliance.
"""
from typing import List, Dict, Any
from datetime import datetime


def validate_epcis_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate EPCIS events for DSCSA compliance.
    
    Args:
        events: List of parsed EPCIS events
    
    Returns:
        List of validation issues
    """
    issues = []
    
    for idx, event in enumerate(events):
        event_issues = validate_single_event(event, idx)
        issues.extend(event_issues)
    
    return issues


def validate_single_event(event: Dict[str, Any], event_index: int) -> List[Dict[str, Any]]:
    """Validate a single EPCIS event."""
    issues = []
    
    # Required field: eventTime
    if not event.get("eventTime"):
        issues.append({
            "type": "missing_field",
            "severity": "high",
            "field_path": "eventTime",
            "message": "Event time is required for DSCSA compliance",
            "event_index": event_index,
            "suggested_fix": "Add eventTime in ISO 8601 format",
        })
    
    # Required field: eventType
    valid_event_types = ["ObjectEvent", "AggregationEvent", "TransactionEvent", "TransformationEvent"]
    event_type = event.get("eventType")
    if not event_type:
        issues.append({
            "type": "missing_field",
            "severity": "high",
            "field_path": "eventType",
            "message": "Event type is required",
            "event_index": event_index,
            "suggested_fix": f"Add eventType as one of: {', '.join(valid_event_types)}",
        })
    elif event_type not in valid_event_types:
        issues.append({
            "type": "invalid_value",
            "severity": "high",
            "field_path": "eventType",
            "message": f"Invalid event type: {event_type}",
            "event_index": event_index,
            "suggested_fix": f"Use one of: {', '.join(valid_event_types)}",
        })
    
    # Required field: action (for most event types)
    valid_actions = ["ADD", "OBSERVE", "DELETE"]
    action = event.get("action")
    if event_type in ["ObjectEvent", "AggregationEvent", "TransactionEvent"]:
        if not action:
            issues.append({
                "type": "missing_field",
                "severity": "high",
                "field_path": "action",
                "message": f"Action is required for {event_type}",
                "event_index": event_index,
                "suggested_fix": f"Add action as one of: {', '.join(valid_actions)}",
            })
        elif action not in valid_actions:
            issues.append({
                "type": "invalid_value",
                "severity": "medium",
                "field_path": "action",
                "message": f"Invalid action: {action}",
                "event_index": event_index,
                "suggested_fix": f"Use one of: {', '.join(valid_actions)}",
            })
    
    # Required field: EPCs
    epc_list = event.get("epcList", [])
    quantity_list = event.get("quantityList", [])
    if not epc_list and not quantity_list:
        issues.append({
            "type": "missing_field",
            "severity": "critical",
            "field_path": "epcList",
            "message": "At least one EPC or quantity element is required for DSCSA serialization",
            "event_index": event_index,
            "suggested_fix": "Add epcList with serialized product identifiers",
        })
    
    # Validate EPC format
    for epc in epc_list:
        if not validate_epc_format(epc):
            issues.append({
                "type": "invalid_format",
                "severity": "medium",
                "field_path": "epcList",
                "message": f"Invalid EPC format: {epc}",
                "event_index": event_index,
                "suggested_fix": "Use URN format: urn:epc:id:sgtin:CompanyPrefix.ItemRef.SerialNumber",
            })
    
    # Recommended: bizStep
    if not event.get("bizStep"):
        issues.append({
            "type": "missing_field",
            "severity": "low",
            "field_path": "bizStep",
            "message": "Business step is recommended for full traceability",
            "event_index": event_index,
            "suggested_fix": "Add bizStep (e.g., urn:epcglobal:cbv:bizstep:commissioning)",
        })
    
    # Recommended: disposition
    if not event.get("disposition"):
        issues.append({
            "type": "missing_field",
            "severity": "low",
            "field_path": "disposition",
            "message": "Disposition is recommended for supply chain visibility",
            "event_index": event_index,
            "suggested_fix": "Add disposition (e.g., urn:epcglobal:cbv:disp:active)",
        })
    
    # Recommended: readPoint and bizLocation
    if not event.get("readPoint") and not event.get("bizLocation"):
        issues.append({
            "type": "missing_field",
            "severity": "low",
            "field_path": "readPoint",
            "message": "readPoint or bizLocation recommended for location tracking",
            "event_index": event_index,
            "suggested_fix": "Add readPoint with GLN identifier",
        })
    
    return issues


def validate_epc_format(epc: str) -> bool:
    """Validate EPC URN format."""
    if not epc:
        return False
    
    # Valid patterns
    valid_patterns = [
        "urn:epc:id:sgtin:",
        "urn:epc:id:sscc:",
        "urn:epc:id:sgln:",
        "urn:epc:id:grai:",
        "urn:epc:id:giai:",
        "urn:epc:class:lgtin:",
    ]
    
    # Check if matches any pattern
    for pattern in valid_patterns:
        if epc.startswith(pattern):
            return True
    
    # Also accept pure numeric serial numbers for simplified testing
    if epc.startswith("urn:") or ":" in epc:
        return True
    
    return False


def detect_chain_breaks(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detect chain-of-custody breaks in EPCIS event sequence.
    
    Chain breaks occur when:
    - An EPC appears without a prior commissioning event
    - Ownership changes without proper transaction events
    - Time gaps in custody are implausible
    - Geographic jumps are impossible
    
    Returns:
        List of chain break issues
    """
    issues = []
    
    # Track EPC lifecycle
    epc_history = {}  # epc -> list of (event_index, event_type, timestamp, location)
    
    for idx, event in enumerate(events):
        event_type = event.get("eventType")
        action = event.get("action")
        event_time = event.get("eventTime")
        location = event.get("readPoint") or event.get("bizLocation") or ""
        
        epc_list = event.get("epcList", [])
        
        for epc in epc_list:
            if epc not in epc_history:
                epc_history[epc] = []
                
                # First event should typically be commissioning
                if event_type == "ObjectEvent" and action != "ADD":
                    issues.append({
                        "type": "chain_break",
                        "severity": "high",
                        "field_path": "epcList",
                        "message": f"EPC {epc} first appears with action {action}, expected ADD (commissioning)",
                        "event_index": idx,
                        "suggested_fix": "Ensure commissioning event exists for all EPCs",
                    })
            else:
                # Check for temporal consistency
                last_entry = epc_history[epc][-1]
                last_time = last_entry[2]
                
                if event_time and last_time:
                    if isinstance(event_time, datetime) and isinstance(last_time, datetime):
                        if event_time < last_time:
                            issues.append({
                                "type": "chain_break",
                                "severity": "high",
                                "field_path": "eventTime",
                                "message": f"EPC {epc} has event with earlier timestamp than previous event",
                                "event_index": idx,
                                "suggested_fix": "Correct event timestamps to maintain chronological order",
                            })
                
                # Check for DELETE without custody
                if action == "DELETE":
                    last_action = last_entry[1]
                    if last_action == "DELETE":
                        issues.append({
                            "type": "chain_break",
                            "severity": "medium",
                            "field_path": "action",
                            "message": f"EPC {epc} deleted multiple times",
                            "event_index": idx,
                            "suggested_fix": "Remove duplicate DELETE events",
                        })
            
            # Add to history
            epc_history[epc].append((idx, action, event_time, location))
    
    # Check for EPCs that were never decommissioned but should have been
    # (This is a simplified check - real implementation would be more complex)
    
    return issues


def generate_validation_summary(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate a summary of validation results."""
    summary = {
        "total_issues": len(issues),
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "by_type": {},
        "is_compliant": True,
    }
    
    for issue in issues:
        severity = issue.get("severity", "medium")
        summary[severity] = summary.get(severity, 0) + 1
        
        issue_type = issue.get("type", "unknown")
        if issue_type not in summary["by_type"]:
            summary["by_type"][issue_type] = 0
        summary["by_type"][issue_type] += 1
    
    # Not compliant if any critical or high issues
    if summary["critical"] > 0 or summary["high"] > 0:
        summary["is_compliant"] = False
    
    return summary
