"""Small authentication boundary shared by HTTP and WebSocket adapters."""


class WorkerAuthenticationError(RuntimeError):
    """Provisioned identity/token was rejected; retrying it cannot authenticate."""


def authentication_headers(worker_id, token) -> dict[str, str]:
    validate_worker_id(worker_id)
    return {
        "Authorization": f"Bearer {token.get_secret_value()}",
        "X-Worker-ID": worker_id,
    }


def validate_worker_id(worker_id):
    if not isinstance(worker_id, str) or not 1 <= len(worker_id) <= 256:
        raise ValueError(
            "Worker ID must be a nonempty string of at most 256 characters"
        )
    if any(not 33 <= ord(character) <= 126 for character in worker_id):
        raise ValueError("Worker ID must contain printable ASCII without spaces")
    return worker_id
