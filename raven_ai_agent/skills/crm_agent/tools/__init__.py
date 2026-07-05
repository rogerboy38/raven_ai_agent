"""
CRM Tools
=========
Pure functions used by sub-agents and exposed to LLM function-calling.
Each is whitelisted so it also works from the ERPNext UI / REST API.
"""
from . import leads, opportunities, contacts, communications, activities, parsing  # noqa: F401
