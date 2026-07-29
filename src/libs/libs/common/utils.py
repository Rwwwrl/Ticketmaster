import json
from typing import Any


def dumps_to_canonical_json(obj: Any) -> bytes:
    """Serialize to deterministic JSON: sorted keys and no insignificant whitespace."""
    return json.dumps(obj=obj, sort_keys=True, separators=(",", ":")).encode()
