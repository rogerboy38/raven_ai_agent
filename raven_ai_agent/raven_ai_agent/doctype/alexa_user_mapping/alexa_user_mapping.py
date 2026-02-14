# Copyright (c) 2026, Raven AI Agent and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AlexaUserMapping(Document):
    """DocType for mapping Alexa user IDs to Frappe users and Raven channels."""

    def validate(self):
        """Validate the mapping before saving."""
        # Ensure channel name is lowercase and doesn't have # prefix
        if self.default_channel:
            self.default_channel = self.default_channel.lstrip("#").lower()

    def before_save(self):
        """Clean up data before saving."""
        # Strip whitespace from alexa_user_id
        if self.alexa_user_id:
            self.alexa_user_id = self.alexa_user_id.strip()


def get_mapping_for_alexa_user(alexa_user_id: str) -> dict | None:
    """
    Get the Frappe user and channel mapping for an Alexa user ID.

    Args:
        alexa_user_id: The Alexa user ID (e.g. amzn1.account.ABC123)

    Returns:
        dict with frappe_user, default_workspace, default_channel or None if not found
    """
    if not alexa_user_id:
        return None

    mapping = frappe.get_all(
        "Alexa User Mapping",
        filters={"alexa_user_id": alexa_user_id, "enabled": 1},
        fields=["name", "frappe_user", "default_workspace", "default_channel"],
        limit=1,
    )

    return mapping[0] if mapping else None
