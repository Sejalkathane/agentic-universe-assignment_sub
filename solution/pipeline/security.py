import base64, hashlib, hmac, json, os, sys
from cryptography.fernet import Fernet


class PII:
    """HMAC for matching (deterministic, keyed); Fernet for recoverable storage."""
    def __init__(self, secret: str | None = None):
        secret = secret or os.environ.get("AU_PII_SECRET")
        if not secret:
            print("WARNING: AU_PII_SECRET not set; using dev secret", file=sys.stderr)
            secret = "dev-only-secret"
        s = secret.encode()
        self._mac = hashlib.sha256(b"mac|" + s).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"enc|" + s).digest()))

    def hash_phone(self, phone: str) -> str:
        return hmac.new(self._mac, phone.encode(), hashlib.sha256).hexdigest()

    def encrypt(self, obj) -> str:
        return self._fernet.encrypt(json.dumps(obj).encode()).decode()

    def decrypt(self, token: str):
        return json.loads(self._fernet.decrypt(token.encode()))