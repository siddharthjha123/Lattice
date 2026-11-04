"""Only the team-owned shared wire protocol is accepted or emitted."""

from shared.contracts import (
    CONTROL_PLANE_COMMAND_ADAPTER,
    CONTROL_PLANE_MESSAGE_ADAPTER,
    WORKER_MESSAGE_ADAPTER,
)


def decode_command(raw: str | bytes):
    return CONTROL_PLANE_COMMAND_ADAPTER.validate_json(raw)


def encode_message(message) -> str:
    # Revalidation prevents an internal model or untyped dict becoming a new protocol.
    validated = WORKER_MESSAGE_ADAPTER.validate_python(message)
    return validated.model_dump_json(exclude_none=True)


def decode_control_message(raw: str | bytes):
    return CONTROL_PLANE_MESSAGE_ADAPTER.validate_json(raw)
