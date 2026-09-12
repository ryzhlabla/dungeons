import hashlib
from aiogram.types import FSInputFile
from .content import ROOT


class Media:
    def __init__(self, content):
        self.registry = content["media"]
        self.cache = {}

    def resolve(self, asset):
        path = ROOT / self.registry[asset]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        key = (asset, digest)
        return key, self.cache.get(key) or FSInputFile(path)

    def remember(self, key, message):
        if message.photo:
            # Keep only the latest version of each asset.
            self.cache = {k: v for k, v in self.cache.items() if k[0] != key[0]}
            self.cache[key] = message.photo[-1].file_id
