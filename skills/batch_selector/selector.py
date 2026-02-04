"""Batch Selector for Raven AI Agent.

This module provides batch selection functionality that integrates
with Frappe/ERPNext to retrieve batch information using golden numbers.

Core Functions:
    - select_batch: Main selection logic
    - query_frappe_batch: API call to Frappe
    - format_response: Structures response for AI agent
"""

import json
import requests
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import logging

from .parsers import parse_golden_number, GoldenNumberParser, ParsedGoldenNumber


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class BatchInfo:
    """Structured batch information."""
    golden_number: str
    item_code: str = ""
    item_name: str = ""
    batch_qty: float = 0.0
    manufacturing_date: Optional[str] = None
    expiry_date: Optional[str] = None
    status: str = "Unknown"
    warehouse: str = ""
    supplier: str = ""
    additional_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "golden_number": self.golden_number,
            "item_code": self.item_code,
            "item_name": self.item_name,
            "batch_qty": self.batch_qty,
            "manufacturing_date": self.manufacturing_date,
            "expiry_date": self.expiry_date,
            "status": self.status,
            "warehouse": self.warehouse,
            "supplier": self.supplier,
            "additional_data": self.additional_data
        }


@dataclass
class SelectionResult:
    """Result of a batch selection operation."""
    success: bool
    batch: Optional[BatchInfo] = None
    batches: List[BatchInfo] = field(default_factory=list)
    message: str = ""
    error_code: Optional[str] = None
    search_type: str = ""
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "success": self.success,
            "message": self.message,
            "search_type": self.search_type,
            "confidence": self.confidence
        }
        if self.batch:
            result["batch"] = self.batch.to_dict()
        if self.batches:
            result["batches"] = [b.to_dict() for b in self.batches]
        if self.error_code:
            result["error_code"] = self.error_code
        return result


class BatchSelector:
    """Main class for batch selection operations."""
    
    def __init__(
        self,
        frappe_url: str,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        default_company_code: str = "01",
        cache_enabled: bool = True,
        cache_ttl: int = 300
    ):
        self.frappe_url = frappe_url.rstrip('/')
        self.api_key = api_key
        self.api_secret = api_secret
        self.parser = GoldenNumberParser(default_company_code=default_company_code)
        self.cache_enabled = cache_enabled
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple] = {}
    
    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key and self.api_secret:
            headers["Authorization"] = f"token {self.api_key}:{self.api_secret}"
        return headers
    
    def select(self, input_string: str) -> SelectionResult:
        parsed = self.parser.parse(input_string)
        if not parsed.valid:
            return SelectionResult(success=False, message=parsed.error_message or "Could not parse input", error_code="PARSE_ERROR")
        
        if parsed.search_type in ["exact", "partial"]:
            result = self._search_exact(parsed.golden_number)
        elif parsed.search_type == "date_range":
            result = self._search_by_date_range(parsed.components["start_date"], parsed.components["end_date"])
        elif parsed.search_type == "fuzzy":
            result = self._search_by_product_name(parsed.components["product_name"])
        else:
            result = SelectionResult(success=False, message=f"Unsupported search type: {parsed.search_type}", error_code="UNSUPPORTED_SEARCH")
        
        result.search_type = parsed.search_type
        result.confidence = parsed.confidence
        return result
    
    def _search_exact(self, golden_number: str) -> SelectionResult:
        try:
            batch_data = self._query_frappe("Batch", filters={"batch_id": golden_number}, fields=["*"])
            if not batch_data:
                return SelectionResult(success=False, message=f"Batch not found: {golden_number}", error_code="NOT_FOUND")
            batch = self._parse_batch_data(batch_data[0], golden_number)
            return SelectionResult(success=True, batch=batch, message="Batch found successfully")
        except Exception as e:
            logger.error(f"Error searching for batch {golden_number}: {e}")
            return SelectionResult(success=False, message=f"Error: {str(e)}", error_code="API_ERROR")
    
    def _search_by_date_range(self, start_date: str, end_date: str) -> SelectionResult:
        try:
            batch_data = self._query_frappe("Batch", filters=[["manufacturing_date", ">=", start_date], ["manufacturing_date", "<=", end_date]], fields=["*"], limit=100)
            if not batch_data:
                return SelectionResult(success=False, message=f"No batches found between {start_date} and {end_date}", error_code="NOT_FOUND")
            batches = [self._parse_batch_data(data, data.get("batch_id", "")) for data in batch_data]
            return SelectionResult(success=True, batches=batches, message=f"Found {len(batches)} batches")
        except Exception as e:
            return SelectionResult(success=False, message=f"Error: {str(e)}", error_code="API_ERROR")
    
    def _search_by_product_name(self, product_name: str) -> SelectionResult:
        try:
            items = self._query_frappe("Item", filters=[["item_name", "like", f"%{product_name}%"]], fields=["name", "item_name"])
            if not items:
                return SelectionResult(success=False, message=f"No items found matching: {product_name}", error_code="NOT_FOUND")
            item_codes = [item["name"] for item in items]
            batch_data = self._query_frappe("Batch", filters=[["item", "in", item_codes]], fields=["*"], limit=50)
            if not batch_data:
                return SelectionResult(success=False, message=f"No batches found for: {product_name}", error_code="NOT_FOUND")
            batches = [self._parse_batch_data(data, data.get("batch_id", "")) for data in batch_data]
            return SelectionResult(success=True, batches=batches, message=f"Found {len(batches)} batches")
        except Exception as e:
            return SelectionResult(success=False, message=f"Error: {str(e)}", error_code="API_ERROR")
    
    def _query_frappe(self, doctype: str, filters: Any = None, fields: List[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        url = f"{self.frappe_url}/api/resource/{doctype}"
        params = {"limit_page_length": limit}
        if filters:
            params["filters"] = json.dumps(filters)
        if fields:
            params["fields"] = json.dumps(fields)
        response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
        response.raise_for_status()
        return response.json().get("data", [])
    
    def _parse_batch_data(self, data: Dict[str, Any], golden_number: str) -> BatchInfo:
        return BatchInfo(
            golden_number=golden_number,
            item_code=data.get("item", ""),
            item_name=data.get("item_name", data.get("item", "")),
            batch_qty=float(data.get("batch_qty", 0)),
            manufacturing_date=data.get("manufacturing_date"),
            expiry_date=data.get("expiry_date"),
            status="Active" if not data.get("disabled") else "Disabled",
            warehouse=data.get("warehouse", ""),
            supplier=data.get("supplier", "")
        )


# Module-level convenience functions
_default_selector: Optional[BatchSelector] = None


def select_batch(input_string: str) -> Dict[str, Any]:
    """Select a batch using the default selector."""
    if not _default_selector:
        raise RuntimeError("Selector not configured. Call configure_selector first.")
    result = _default_selector.select(input_string)
    return result.to_dict()


def query_frappe_batch(golden_number: str) -> Dict[str, Any]:
    """Query Frappe for a specific batch by golden number."""
    if not _default_selector:
        raise RuntimeError("Selector not configured. Call configure_selector first.")
    result = _default_selector._search_exact(golden_number)
    return result.to_dict()


def format_response(result: SelectionResult) -> Dict[str, Any]:
    """Format a SelectionResult for AI agent consumption."""
    return result.to_dict()
