import re
import uuid


def sanitize_filename(name: str) -> str:
    """Sanitize a user-provided filename to prevent path traversal and injection.

    Keeps alphanumeric characters, dots, dashes, and underscores.
    Replaces everything else with underscores. Truncates stem to 64 chars,
    extension to 10 chars.
    """
    name = name.strip()
    if "." in name:
        stem, _, ext = name.rpartition(".")
        stem = re.sub(r"[^\w\-]", "_", stem)[:64]
        ext = re.sub(r"[^\w]", "", ext)[:10]
        return f"{stem}.{ext}" if ext else stem
    return re.sub(r"[^\w\-]", "_", name)[:64]


def generate_key(collection: str, record_id: str, field: str, filename: str) -> str:
    """Generate a unique, safe storage key for a file.

    Format: {collection}/{record_id}/{field}/{uuid}_{sanitized_filename}
    The UUID prefix guarantees uniqueness; the original filename aids debugging.
    User-provided filenames are sanitized — never used verbatim in the key.
    """
    safe_name = sanitize_filename(filename)
    uid = uuid.uuid4().hex
    return f"{collection}/{record_id}/{field}/{uid}_{safe_name}"
