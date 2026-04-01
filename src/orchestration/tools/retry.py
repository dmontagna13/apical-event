"""Tool call retry prompt construction."""

from __future__ import annotations

import json


def build_retry_prompt(tool_name: str, arguments: dict, errors: list[str]) -> str:
    """Build a re-prompt message for a failed tool call (§5.2).

    The message instructs the Moderator to correct its tool call parameters.
    It includes the tool name, the invalid arguments, and the specific errors.
    """

    args_str = json.dumps(arguments, indent=2, default=str)
    errors_str = "\n".join(f"- {error}" for error in errors)

    return (
        f"Your last tool call to '{tool_name}' was invalid. "
        "Please retry with corrected parameters.\n\n"
        f"Invalid arguments:\n{args_str}\n\n"
        f"Errors:\n{errors_str}"
    )
