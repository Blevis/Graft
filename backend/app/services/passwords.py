"""Password sign-in for the fictional demo accounts only.

Passwords are stored as salted scrypt hashes (standard library, no extra dependency) and compared in constant time.
Production organisations sign in with OIDC; password login is refused outside AUTH_MODE=demo and for any account
that is not a member of a demo organisation."""
import base64
import hashlib
import hmac
import re
import secrets
import time
import unicodedata
from collections import defaultdict, deque
from threading import Lock

# scrypt cost: 2^14 * 8 * 128 B = 16 MiB per hash, ~50 ms. Encoded in the hash so it can be raised later.
_N, _R, _P = 2 ** 14, 8, 1
MIN_LENGTH = 8


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(_N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        # Spend comparable time so a missing account is not distinguishable by timing.
        hashlib.scrypt(password.encode("utf-8"), salt=b"0" * 16, n=_N, r=_R, p=_P, dklen=32)
        return False
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                                dklen=len(base64.b64decode(digest)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, base64.b64decode(digest))


def demo_email(name: str, domain: str) -> str:
    """'Elira Dervishi' -> 'elira.dervishi@<domain>'. Fictional people, reserved .example domains."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", ".", ascii_name.lower()).strip(".") + "@" + domain


class LoginThrottle:
    """At most `limit` failed attempts per email in `window` seconds (per process). A success clears the count."""

    def __init__(self, limit: int = 5, window: float = 900.0):
        self.limit, self.window = limit, window
        self._failures: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def _trim(self, key: str, now: float) -> deque:
        q = self._failures[key]
        while q and now - q[0] > self.window:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._trim(key, time.monotonic())) >= self.limit

    def failed(self, key: str) -> None:
        with self._lock:
            self._trim(key, time.monotonic()).append(time.monotonic())

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


throttle = LoginThrottle()


_demo_hash: tuple[str, str] | None = None


def demo_password_hash(password: str) -> str:
    """One hash per process for the shared demo password. Every demo account knowingly shares this public password,
    so sharing its salt reveals nothing; it keeps seeding and test resets fast."""
    global _demo_hash
    if _demo_hash is None or _demo_hash[0] != password:
        _demo_hash = (password, hash_password(password))
    return _demo_hash[1]
