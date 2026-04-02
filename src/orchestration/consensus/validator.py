"""Consensus output validation against the output contract (§7.4)."""

from __future__ import annotations

from core.schemas.packet import OutputContract


def validate_consensus(output: dict, output_contract: OutputContract) -> list[str]:
    """Validate a consensus output dict against the output contract.

    Returns a list of error/warning strings.  An empty list means the output
    satisfies all hard constraints.

    - Missing return_header fields → error
    - Missing required sections → error
    - Section below minimum count → error
    - stop_condition_met is False → WARNING (prefixed "Warning:"), not a hard error
    """
    errors: list[str] = []

    # 1. Return header fields
    return_header = output.get("return_header", {})
    for field in output_contract.return_header_fields:
        if field not in return_header or return_header[field] is None:
            errors.append(f"Missing return_header field: '{field}'")

    # 2. Required sections
    sections: dict = output.get("sections", {})
    for section in output_contract.required_sections:
        if section not in sections:
            errors.append(f"Missing required section: '{section}'")

    # 3. Minimum counts
    for count_key, minimum in (output_contract.minimum_counts or {}).items():
        count = _count_for_key(sections, count_key)
        if count is None:
            errors.append(f"Cannot determine item count for minimum_counts key: '{count_key}'")
        elif count < minimum:
            errors.append(f"Section '{count_key}' has {count} items but minimum is {minimum}")

    # 4. Stop condition (warning only — does not trigger retry)
    if not output.get("stop_condition_met", False):
        errors.append(
            "Warning: stop_condition_met is False (consensus forced before stop condition)"
        )

    return errors


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _count_for_key(sections: dict, count_key: str) -> int | None:
    """Return item count for a minimum_counts key.

    Try exact section name first; fall back to prefix match so that
    compound keys like "DECISION_ROADMAP_GATES" resolve against the
    "DECISION_ROADMAP" section.
    """
    # Exact match
    if count_key in sections:
        return _count_list_items(sections[count_key])

    # Prefix match: e.g. "DECISION_ROADMAP_GATES" → section "DECISION_ROADMAP"
    for section_name, section_data in sections.items():
        if count_key.startswith(section_name + "_") or count_key == section_name:
            return _count_list_items(section_data)

    return None


def _count_list_items(section_data: object) -> int | None:
    """Return the length of the first list value found in section_data."""
    if isinstance(section_data, list):
        return len(section_data)
    if isinstance(section_data, dict):
        for value in section_data.values():
            if isinstance(value, list):
                return len(value)
    return None
