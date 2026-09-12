"""Development-only, atomic reload of editable text; game rules stay fixed."""
import hashlib
import json
import logging
from pathlib import Path
from string import Formatter

from .content import ROOT, load_content
from .validate import validate_rendered_content

log = logging.getLogger("dungeon.text_reload")


def env_flag(value):
    value = value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("DEV_TEXT_RELOAD must be true or false")


def validate_text_shape(old, new, path):
    if type(old) is not type(new):
        raise ValueError(f"Text type changed: {path}")
    if isinstance(old, dict):
        if old.keys() != new.keys():
            raise ValueError(f"Text keys changed: {path}")
        for key in old:
            validate_text_shape(old[key], new[key], f"{path}/{key}")
    elif isinstance(old, list):
        if len(old) != len(new):
            raise ValueError(f"Text list length changed: {path}")
        for i, (before, after) in enumerate(zip(old, new)):
            validate_text_shape(before, after, f"{path}/{i}")
    elif isinstance(old, str):
        if len(new) > 1024:
            raise ValueError(f"Text exceeds caption limit: {path}")
        def fields(text):
            return {(field, spec, conversion) for _, field, spec, conversion in Formatter().parse(text) if field is not None}
        if fields(old) != fields(new):
            raise ValueError(f"Template placeholders changed: {path}")


class TextContentSource:
    def __init__(self, initial, enabled=False, root=ROOT, on_reload=None):
        self.current = initial
        self.enabled = enabled
        self.root = Path(root)
        self.on_reload = on_reload
        self._manifest = initial["_manifest"]
        self._baseline = initial["_text_sources"]
        self._fingerprint = None
        self.last_error = None

    def get(self):
        if not self.enabled:
            return self.current
        try:
            # Read each file once; validate and assemble from these exact bytes.
            files = {path: (self.root / path).read_bytes() for path in self._baseline}
            fingerprint = tuple((path, hashlib.sha256(data).digest()) for path, data in sorted(files.items()))
            if fingerprint == self._fingerprint:
                return self.current
            sources = {}
            for path, data in files.items():
                try:
                    sources[path] = json.loads(data.decode("utf-8-sig"))
                    validate_text_shape(self._baseline[path], sources[path], path)
                except (ValueError, UnicodeError) as exc:
                    raise ValueError(f"Invalid text file {path}: {type(exc).__name__}") from exc
            candidate = load_content(self._manifest, sources)
            validate_rendered_content(candidate)
        except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
            error = str(exc)
            if error != self.last_error:
                log.warning("Text reload rejected; keeping last valid content: %s", error)
            self.last_error = error
            return self.current
        # No await or in-place mutation: each callback uses a single immutable snapshot.
        self.current = candidate
        self._fingerprint = fingerprint
        self.last_error = None
        if self.on_reload:
            try:
                self.on_reload(candidate)
            except OSError as exc:
                log.warning("Texts reloaded but map update failed: %s", type(exc).__name__)
        log.info("Editable texts reloaded.")
        return self.current

