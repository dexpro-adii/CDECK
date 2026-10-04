"""
Session PII vault.

What this replaces
------------------
The vault used to be two module-level dicts holding raw PII:

    vault_store  = defaultdict(dict)   # session_id -> {placeholder: RAW VALUE}
    vault_counts = defaultdict(lambda: defaultdict(int))

Aadhaar, PAN and UPI values sat in plaintext process memory, for the life of the
process, with no key involved anywhere -- so there was nothing to rotate and
nothing to revoke. This module keeps the same external behaviour but stores
ciphertext, gives the key a lifecycle, and bounds how long values live.

What this is NOT
----------------
This is not a KMS integration and does not pretend to be. The keys still live in
the process's environment, so anyone who can read the process can read the keys.
See the "Vault key custody" section of the README for the gap list and what a
real hardening plan looks like.
"""

from __future__ import annotations

import hmac
import os
import secrets
import sys
import threading
import time
from collections import defaultdict

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

PRIMARY_KEY_ENV = "CDECK_VAULT_KEY"
LEGACY_KEY_ENV = "PROMPTKAVACH_VAULT_KEY"
RETIRED_KEYS_ENV = "CDECK_VAULT_RETIRED_KEYS"

DEFAULT_TTL_SECONDS = 3600      # PII is evicted an hour after it is vaulted
DEFAULT_MAX_SESSIONS = 5000     # bound on total retained sessions


def _load_cipher():
    """
    Builds the MultiFernet used for vault values.

    The first key encrypts; every key can decrypt. That is the rotation path:
    move the old key into CDECK_VAULT_RETIRED_KEYS, put a fresh one in
    CDECK_VAULT_KEY, and previously issued tokens keep resolving.

    With no key configured we generate an ephemeral one and say so loudly --
    a restart then makes old tokens unresolvable, which is the safe failure
    (values become unrecoverable rather than silently readable).
    """
    primary = (os.environ.get(PRIMARY_KEY_ENV) or os.environ.get(LEGACY_KEY_ENV) or "").strip()
    ephemeral = False

    if not primary:
        primary = Fernet.generate_key().decode()
        ephemeral = True
        print(
            f"WARNING: {PRIMARY_KEY_ENV} is not set. Generated an EPHEMERAL vault key.\n"
            f"         Vaulted PII will not survive a restart, and multiple workers\n"
            f"         will not share a key. Set {PRIMARY_KEY_ENV} before deploying.",
            file=sys.stderr,
        )

    keys = []
    try:
        keys.append(Fernet(primary.encode() if isinstance(primary, str) else primary))
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            f"{PRIMARY_KEY_ENV} is not a valid Fernet key. Generate one with:\n"
            f"  python -c \"from cryptography.fernet import Fernet; "
            f"print(Fernet.generate_key().decode())\""
        ) from exc

    for raw in (os.environ.get(RETIRED_KEYS_ENV) or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            keys.append(Fernet(raw.encode()))
        except (ValueError, TypeError):
            print(f"WARNING: ignoring malformed key in {RETIRED_KEYS_ENV}", file=sys.stderr)

    return MultiFernet(keys), ephemeral, len(keys)


class SessionVault:
    """Encrypted, TTL-bounded placeholder -> PII store."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS,
                 max_sessions: int = DEFAULT_MAX_SESSIONS):
        self._cipher, self.ephemeral_key, self.key_count = _load_cipher()
        self._ttl = ttl_seconds
        self._max_sessions = max_sessions
        self._lock = threading.Lock()
        # session_id -> {placeholder: (ciphertext, stored_at)}
        self._store: dict = defaultdict(dict)
        self._counts: dict = defaultdict(lambda: defaultdict(int))
        self._touched: dict = {}
        # session_id -> bearer secret minted when the session is first written.
        # Holding this is what proves ownership of the session at resolve time;
        # a session_id on its own is not a credential.
        self._tokens: dict = {}

    # ------------------------------------------------------------------ internals
    def _purge_locked(self, now: float) -> None:
        expired = [sid for sid, ts in self._touched.items() if now - ts > self._ttl]
        for sid in expired:
            self._forget_locked(sid)

        # hard cap: drop least-recently-touched sessions
        while len(self._touched) > self._max_sessions:
            self._forget_locked(min(self._touched, key=self._touched.get))

    def _forget_locked(self, session_id: str) -> None:
        self._store.pop(session_id, None)
        self._counts.pop(session_id, None)
        self._touched.pop(session_id, None)
        self._tokens.pop(session_id, None)

    # ------------------------------------------------------------------ ownership
    def session_token(self, session_id: str) -> str:
        """
        Returns the bearer secret for a session, minting one on first use.

        Handed back to whoever created the session; /vault/resolve will not
        return plaintext without it.
        """
        with self._lock:
            token = self._tokens.get(session_id)
            if token is None:
                token = secrets.token_urlsafe(32)
                self._tokens[session_id] = token
            return token

    def verify(self, session_id: str, presented) -> bool:
        """
        Constant-time check that `presented` owns `session_id`.

        Unknown sessions return False rather than raising, so a caller cannot
        tell "wrong token" from "no such session" and enumerate session ids.
        """
        if not presented or not isinstance(presented, str):
            return False
        with self._lock:
            expected = self._tokens.get(session_id)
        if expected is None:
            # still burn a comparison so timing does not reveal existence
            hmac.compare_digest(presented, presented)
            return False
        return hmac.compare_digest(expected, presented)

    # -------------------------------------------------------------------- public
    def next_placeholder(self, session_id: str, entity_type: str) -> str:
        with self._lock:
            self._counts[session_id][entity_type] += 1
            return f"<{entity_type}_{self._counts[session_id][entity_type]}>"

    def store(self, session_id: str, placeholder: str, value: str) -> None:
        now = time.time()
        token = self._cipher.encrypt(value.encode("utf-8"))
        with self._lock:
            self._store[session_id][placeholder] = (token, now)
            self._touched[session_id] = now
            # purge after inserting, so the cap holds for the resulting state
            # rather than the pre-insert one
            self._purge_locked(now)

    def resolve_text(self, session_id: str, text: str) -> str:
        """Substitutes every placeholder this session owns back into text."""
        now = time.time()
        with self._lock:
            self._purge_locked(now)
            entries = dict(self._store.get(session_id, {}))
            if entries:
                self._touched[session_id] = now

        for placeholder, (token, _) in entries.items():
            if placeholder not in text:
                continue
            try:
                text = text.replace(placeholder, self._cipher.decrypt(token).decode("utf-8"))
            except InvalidToken:
                # key rotated out entirely -- leave the placeholder in place
                # rather than failing the request or leaking a partial value
                continue
        return text

    def rotate(self, new_key: str) -> None:
        """
        Re-encrypts every stored value under new_key, which becomes primary.
        Exposed for tests and for an operational rotation script.
        """
        new_cipher = MultiFernet([Fernet(new_key.encode())] + list(self._cipher._fernets))
        with self._lock:
            for session in self._store.values():
                for placeholder, (token, ts) in list(session.items()):
                    session[placeholder] = (new_cipher.rotate(token), ts)
            self._cipher = new_cipher
            self.key_count += 1

    # ------------------------------------------------------------------ introspection
    def stats(self) -> dict:
        with self._lock:
            return {
                "sessions": len(self._store),
                "entries": sum(len(v) for v in self._store.values()),
                "ttl_seconds": self._ttl,
                "max_sessions": self._max_sessions,
                "keys_loaded": self.key_count,
                "ephemeral_key": self.ephemeral_key,
            }
