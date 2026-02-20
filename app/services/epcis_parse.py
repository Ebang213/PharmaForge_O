"""
EPCIS parsing service.
"""
import json
import re
from typing import List, Dict, Any
from datetime import datetime
from defusedxml import ElementTree as ET
from xml.etree.ElementTree import Element  # for type hints only; parsing uses defusedxml


def parse_epcis_file(content: str, file_type: str) -> List[Dict[str, Any]]:
    """
    Parse EPCIS file content (JSON or XML) and extract events.
    
    Args:
        content: File content as string
        file_type: 'json' or 'xml'
    
    Returns:
        List of parsed event dictionaries
    """
    if file_type == 'json':
        return parse_epcis_json(content)
    else:
        return parse_epcis_xml(content)


def parse_epcis_json(content: str) -> List[Dict[str, Any]]:
    """Parse EPCIS JSON format."""
    data = json.loads(content)
    events = []
    
    # Handle EPCIS 2.0 format
    if "epcisBody" in data:
        event_list = data.get("epcisBody", {}).get("eventList", [])
    # Handle array format
    elif isinstance(data, list):
        event_list = data
    # Handle single event
    elif "eventType" in data:
        event_list = [data]
    # Handle events wrapper
    elif "events" in data:
        event_list = data["events"]
    else:
        event_list = []
    
    for event in event_list:
        parsed = parse_single_event(event)
        events.append(parsed)
    
    return events


def parse_epcis_xml(content: str) -> List[Dict[str, Any]]:
    """Parse EPCIS XML format."""
    # Remove namespace prefixes for easier parsing
    content = re.sub(r'xmlns[^"]*"[^"]*"', '', content)
    content = re.sub(r'<(\/?)[a-zA-Z0-9]+:', r'<\1', content)
    
    root = ET.fromstring(content)
    events = []
    
    # Find all event types
    event_types = ['ObjectEvent', 'AggregationEvent', 'TransactionEvent', 'TransformationEvent']
    
    for event_type in event_types:
        for event_elem in root.iter(event_type):
            parsed = parse_xml_event(event_elem, event_type)
            events.append(parsed)
    
    return events


def parse_single_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Parse a single EPCIS event from JSON."""
    event_type = event.get("type") or event.get("eventType") or "ObjectEvent"
    
    # Parse event time
    event_time = event.get("eventTime")
    if event_time and isinstance(event_time, str):
        try:
            event_time = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
        except ValueError:
            pass
    
    # Extract EPCs
    epc_list = []
    if "epcList" in event:
        epc_list = event["epcList"]
    elif "childEPCs" in event:
        epc_list = event["childEPCs"]
    
    # Extract quantity list
    quantity_list = event.get("quantityList", [])
    
    # Extract read point
    read_point = event.get("readPoint", {})
    if isinstance(read_point, dict):
        read_point = read_point.get("id", "")
    
    # Extract business location
    biz_location = event.get("bizLocation", {})
    if isinstance(biz_location, dict):
        biz_location = biz_location.get("id", "")
    
    # Extract source/destination
    source_list = event.get("sourceList", [])
    destination_list = event.get("destinationList", [])
    
    return {
        "eventType": event_type,
        "action": event.get("action"),
        "eventTime": event_time,
        "eventTimeZoneOffset": event.get("eventTimeZoneOffset"),
        "bizStep": event.get("bizStep"),
        "disposition": event.get("disposition"),
        "readPoint": read_point,
        "bizLocation": biz_location,
        "epcList": epc_list,
        "quantityList": quantity_list,
        "sourceList": source_list,
        "destinationList": destination_list,
        "parentID": event.get("parentID"),
        "inputEPCList": event.get("inputEPCList", []),
        "outputEPCList": event.get("outputEPCList", []),
        "raw": event,
    }


def parse_xml_event(elem: Element, event_type: str) -> Dict[str, Any]:
    """Parse XML event element."""
    
    def get_text(path: str) -> str:
        found = elem.find(path)
        return found.text if found is not None and found.text else ""
    
    def get_list(path: str) -> List[str]:
        results = []
        for item in elem.findall(path):
            if item.text:
                results.append(item.text)
        return results
    
    # Parse event time
    event_time = get_text("eventTime")
    if event_time:
        try:
            event_time = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
        except ValueError:
            pass
    
    # Parse quantity list
    quantity_list = []
    for qty_elem in elem.findall(".//quantityElement"):
        quantity_list.append({
            "epcClass": qty_elem.findtext("epcClass"),
            "quantity": float(qty_elem.findtext("quantity") or 0),
            "uom": qty_elem.findtext("uom")
        })
    
    return {
        "eventType": event_type,
        "action": get_text("action"),
        "eventTime": event_time,
        "eventTimeZoneOffset": get_text("eventTimeZoneOffset"),
        "bizStep": get_text("bizStep"),
        "disposition": get_text("disposition"),
        "readPoint": get_text("readPoint/id"),
        "bizLocation": get_text("bizLocation/id"),
        "epcList": get_list(".//epc"),
        "quantityList": quantity_list,
        "sourceList": get_list(".//source"),
        "destinationList": get_list(".//destination"),
        "parentID": get_text("parentID"),
        "inputEPCList": get_list(".//inputEPC"),
        "outputEPCList": get_list(".//outputEPC"),
    }
