"""
Unit tests for EPCIS parsing and validation.
"""
import pytest
import json
from datetime import datetime

from app.services.epcis_parse import (
    parse_epcis_file,
    parse_epcis_json,
    parse_epcis_xml,
)
from app.services.epcis_validate import (
    validate_epcis_events,
    validate_single_event,
    validate_epc_format,
    detect_chain_breaks,
    generate_validation_summary,
)


# ============= Sample Data =============

VALID_JSON_EPCIS = json.dumps({
    "epcisBody": {
        "eventList": [
            {
                "type": "ObjectEvent",
                "eventTime": "2024-12-15T10:00:00Z",
                "action": "ADD",
                "bizStep": "urn:epcglobal:cbv:bizstep:commissioning",
                "disposition": "urn:epcglobal:cbv:disp:active",
                "epcList": ["urn:epc:id:sgtin:0614141.107346.1001"],
                "readPoint": {"id": "urn:epc:id:sgln:0614141.00001.0"},
            }
        ]
    }
})

VALID_XML_EPCIS = """<?xml version="1.0" encoding="UTF-8"?>
<EPCISDocument>
  <EPCISBody>
    <EventList>
      <ObjectEvent>
        <eventTime>2024-12-15T10:00:00Z</eventTime>
        <action>ADD</action>
        <bizStep>urn:epcglobal:cbv:bizstep:commissioning</bizStep>
        <epcList>
          <epc>urn:epc:id:sgtin:0614141.107346.1001</epc>
        </epcList>
      </ObjectEvent>
    </EventList>
  </EPCISBody>
</EPCISDocument>
"""

INVALID_JSON_EPCIS = json.dumps({
    "epcisBody": {
        "eventList": [
            {
                "type": "ObjectEvent",
                # Missing eventTime
                "action": "ADD",
                # Missing epcList
            }
        ]
    }
})


# ============= Parser Tests =============

class TestEPCISParser:
    
    def test_parse_json_epcis(self):
        """Test parsing valid EPCIS JSON."""
        events = parse_epcis_file(VALID_JSON_EPCIS, "json")
        
        assert len(events) == 1
        event = events[0]
        assert event["eventType"] == "ObjectEvent"
        assert event["action"] == "ADD"
        assert event["bizStep"] == "urn:epcglobal:cbv:bizstep:commissioning"
        assert len(event["epcList"]) == 1
        assert event["epcList"][0] == "urn:epc:id:sgtin:0614141.107346.1001"
    
    def test_parse_xml_epcis(self):
        """Test parsing valid EPCIS XML."""
        events = parse_epcis_file(VALID_XML_EPCIS, "xml")
        
        assert len(events) == 1
        event = events[0]
        assert event["eventType"] == "ObjectEvent"
        assert event["action"] == "ADD"
        assert "urn:epc:id:sgtin:0614141.107346.1001" in event["epcList"]
    
    def test_parse_json_array_format(self):
        """Test parsing JSON array format (list of events)."""
        content = json.dumps([
            {"type": "ObjectEvent", "eventTime": "2024-01-01T00:00:00Z", "action": "ADD", "epcList": ["urn:epc:id:sgtin:1.2.3"]}
        ])
        events = parse_epcis_json(content)
        
        assert len(events) == 1
        assert events[0]["eventType"] == "ObjectEvent"
    
    def test_parse_empty_epcis(self):
        """Test parsing empty event list."""
        content = json.dumps({"epcisBody": {"eventList": []}})
        events = parse_epcis_json(content)
        
        assert len(events) == 0
    
    def test_parse_event_time_formats(self):
        """Test various eventTime formats are parsed correctly."""
        content = json.dumps({
            "epcisBody": {
                "eventList": [
                    {"type": "ObjectEvent", "eventTime": "2024-12-15T10:00:00Z", "action": "ADD", "epcList": ["urn:epc:id:sgtin:1.2.3"]},
                    {"type": "ObjectEvent", "eventTime": "2024-12-15T10:00:00+00:00", "action": "ADD", "epcList": ["urn:epc:id:sgtin:1.2.4"]},
                ]
            }
        })
        events = parse_epcis_json(content)
        
        assert len(events) == 2
        assert all(isinstance(e.get("eventTime"), datetime) for e in events)


# ============= Validation Tests =============

class TestEPCISValidation:
    
    def test_validate_valid_event(self):
        """Test validation of a valid event."""
        event = {
            "eventType": "ObjectEvent",
            "eventTime": datetime.now(),
            "action": "ADD",
            "epcList": ["urn:epc:id:sgtin:0614141.107346.1001"],
            "bizStep": "urn:epcglobal:cbv:bizstep:commissioning",
            "disposition": "urn:epcglobal:cbv:disp:active",
            "readPoint": "urn:epc:id:sgln:0614141.00001.0",
        }
        issues = validate_single_event(event, 0)
        
        # Should have no high/critical issues
        high_issues = [i for i in issues if i["severity"] in ["high", "critical"]]
        assert len(high_issues) == 0
    
    def test_validate_missing_event_time(self):
        """Test detection of missing eventTime."""
        event = {
            "eventType": "ObjectEvent",
            "action": "ADD",
            "epcList": ["urn:epc:id:sgtin:0614141.107346.1001"],
        }
        issues = validate_single_event(event, 0)
        
        time_issues = [i for i in issues if i["field_path"] == "eventTime"]
        assert len(time_issues) == 1
        assert time_issues[0]["severity"] == "high"
    
    def test_validate_missing_epc_list(self):
        """Test detection of missing EPC list."""
        event = {
            "eventType": "ObjectEvent",
            "eventTime": datetime.now(),
            "action": "ADD",
            # No epcList or quantityList
        }
        issues = validate_single_event(event, 0)
        
        epc_issues = [i for i in issues if i["field_path"] == "epcList"]
        assert len(epc_issues) == 1
        assert epc_issues[0]["severity"] == "critical"
    
    def test_validate_invalid_event_type(self):
        """Test detection of invalid event type."""
        event = {
            "eventType": "InvalidEvent",
            "eventTime": datetime.now(),
            "action": "ADD",
            "epcList": ["urn:epc:id:sgtin:1.2.3"],
        }
        issues = validate_single_event(event, 0)
        
        type_issues = [i for i in issues if i["field_path"] == "eventType"]
        assert len(type_issues) == 1
        assert "invalid" in type_issues[0]["message"].lower()
    
    def test_validate_epc_format(self):
        """Test EPC format validation."""
        assert validate_epc_format("urn:epc:id:sgtin:0614141.107346.1001") == True
        assert validate_epc_format("urn:epc:id:sscc:0614141.1234567890") == True
        assert validate_epc_format("urn:epc:id:sgln:0614141.00001.0") == True
        assert validate_epc_format("urn:epc:class:lgtin:0614141.107346.lot123") == True
        assert validate_epc_format("invalid-epc-format") == False
        assert validate_epc_format("") == False
    
    def test_validate_multiple_events(self):
        """Test validation of multiple events."""
        events = [
            {"eventType": "ObjectEvent", "eventTime": datetime.now(), "action": "ADD", "epcList": ["urn:epc:id:sgtin:1.2.3"]},
            {"eventType": "AggregationEvent", "eventTime": datetime.now(), "action": "ADD", "epcList": ["urn:epc:id:sgtin:1.2.4"]},
        ]
        issues = validate_epcis_events(events)
        
        # Both events are valid, should only have low-severity recommendations
        high_issues = [i for i in issues if i["severity"] in ["high", "critical"]]
        assert len(high_issues) == 0


# ============= Chain Break Tests =============

class TestChainBreakDetection:
    
    def test_detect_missing_commissioning(self):
        """Test detection of EPC appearing without commissioning event."""
        events = [
            {
                "eventType": "ObjectEvent",
                "action": "OBSERVE",  # First event is OBSERVE, not ADD
                "eventTime": datetime(2024, 12, 15, 10, 0, 0),
                "epcList": ["urn:epc:id:sgtin:0614141.107346.1001"],
            }
        ]
        issues = detect_chain_breaks(events)
        
        chain_issues = [i for i in issues if i["type"] == "chain_break"]
        assert len(chain_issues) == 1
        assert "ADD" in chain_issues[0]["message"] or "commissioning" in chain_issues[0]["message"]
    
    def test_detect_temporal_inconsistency(self):
        """Test detection of events out of chronological order."""
        events = [
            {
                "eventType": "ObjectEvent",
                "action": "ADD",
                "eventTime": datetime(2024, 12, 15, 12, 0, 0),  # Later time
                "epcList": ["urn:epc:id:sgtin:0614141.107346.1001"],
            },
            {
                "eventType": "ObjectEvent",
                "action": "OBSERVE",
                "eventTime": datetime(2024, 12, 15, 10, 0, 0),  # Earlier time
                "epcList": ["urn:epc:id:sgtin:0614141.107346.1001"],
            },
        ]
        issues = detect_chain_breaks(events)
        
        temporal_issues = [i for i in issues if "earlier" in i.get("message", "").lower() or "timestamp" in i.get("message", "").lower()]
        assert len(temporal_issues) >= 1
    
    def test_valid_chain_of_custody(self):
        """Test that valid chain of custody produces no chain breaks."""
        events = [
            {
                "eventType": "ObjectEvent",
                "action": "ADD",
                "eventTime": datetime(2024, 12, 15, 10, 0, 0),
                "epcList": ["urn:epc:id:sgtin:0614141.107346.1001"],
            },
            {
                "eventType": "ObjectEvent",
                "action": "OBSERVE",
                "eventTime": datetime(2024, 12, 15, 12, 0, 0),
                "epcList": ["urn:epc:id:sgtin:0614141.107346.1001"],
            },
        ]
        issues = detect_chain_breaks(events)
        
        # Should have no chain break issues
        assert len(issues) == 0


# ============= Summary Tests =============

class TestValidationSummary:
    
    def test_generate_summary(self):
        """Test summary generation."""
        issues = [
            {"type": "missing_field", "severity": "critical"},
            {"type": "missing_field", "severity": "high"},
            {"type": "invalid_format", "severity": "medium"},
            {"type": "missing_field", "severity": "low"},
        ]
        summary = generate_validation_summary(issues)
        
        assert summary["total_issues"] == 4
        assert summary["critical"] == 1
        assert summary["high"] == 1
        assert summary["medium"] == 1
        assert summary["low"] == 1
        assert summary["is_compliant"] == False  # Has critical/high issues
        assert summary["by_type"]["missing_field"] == 3
        assert summary["by_type"]["invalid_format"] == 1
    
    def test_compliant_summary(self):
        """Test summary with only low-severity issues."""
        issues = [
            {"type": "missing_field", "severity": "low"},
            {"type": "missing_field", "severity": "low"},
        ]
        summary = generate_validation_summary(issues)
        
        assert summary["is_compliant"] == True
        assert summary["critical"] == 0
        assert summary["high"] == 0


# ============= Integration Tests =============

class TestEPCISIntegration:
    
    def test_full_parse_and_validate_json(self):
        """Test full flow: parse JSON and validate."""
        events = parse_epcis_file(VALID_JSON_EPCIS, "json")
        issues = validate_epcis_events(events)
        
        # Valid file should have no critical issues
        critical = [i for i in issues if i["severity"] == "critical"]
        assert len(critical) == 0
    
    def test_full_parse_and_validate_xml(self):
        """Test full flow: parse XML and validate."""
        events = parse_epcis_file(VALID_XML_EPCIS, "xml")
        issues = validate_epcis_events(events)
        
        # Valid file should have no critical issues
        critical = [i for i in issues if i["severity"] == "critical"]
        assert len(critical) == 0
    
    def test_full_parse_and_validate_invalid(self):
        """Test full flow with invalid data."""
        events = parse_epcis_file(INVALID_JSON_EPCIS, "json")
        issues = validate_epcis_events(events)
        
        # Should detect missing eventTime and epcList
        assert len(issues) > 0
        critical = [i for i in issues if i["severity"] == "critical"]
        assert len(critical) > 0  # Missing epcList is critical


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
