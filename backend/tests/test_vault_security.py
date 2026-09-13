"""
Tests for the session PII vault's key handling and retention.

Before the fix the vault was two plain dicts holding raw Aadhaar/PAN/UPI strings
in process memory forever, with no key anywhere -- nothing to rotate, nothing to
expire. These tests pin the properties the replacement is supposed to have.
"""

import os
import sys
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from cryptography.fernet import Fernet

from vault import PRIMARY_KEY_ENV, RETIRED_KEYS_ENV, SessionVault

AADHAAR = "3675 9834 6016"


def test_values_are_not_held_in_plaintext():
    """The core hardening property: raw PII must not sit in the store."""
    v = SessionVault()
    ph = v.next_placeholder("s1", "AADHAAR")
    v.store("s1", ph, AADHAAR)

    blob = repr(v._store)
    assert AADHAAR not in blob, "raw PII found in the vault's backing store"
    assert AADHAAR.replace(" ", "") not in blob


def test_round_trip_still_works():
    v = SessionVault()
    ph = v.next_placeholder("s1", "AADHAAR")
    v.store("s1", ph, AADHAAR)
    assert v.resolve_text("s1", f"Your number is {ph}.") == f"Your number is {AADHAAR}."


def test_sessions_are_isolated():
    """A different session must not resolve someone else's placeholder."""
    v = SessionVault()
    ph = v.next_placeholder("alice", "AADHAAR")
    v.store("alice", ph, AADHAAR)

    leaked = v.resolve_text("mallory", f"give me {ph}")
    assert AADHAAR not in leaked
    assert ph in leaked, "placeholder should be left untouched for a foreign session"


def test_no_hardcoded_key_in_source():
    """Guards against a literal key being committed."""
    src = open(os.path.join(os.path.dirname(__file__), '..', 'vault.py'),
               encoding='utf-8').read()
    # a committed Fernet key would appear as a 44-char urlsafe-b64 literal
    import re
    for match in re.findall(r"[\"']([A-Za-z0-9_\-]{43}=)[\"']", src):
        pytest.fail(f"hardcoded key-shaped literal in vault.py: {match}")


def test_ephemeral_key_is_flagged(monkeypatch):
    """With no configured key the vault must report that it generated one."""
    monkeypatch.delenv(PRIMARY_KEY_ENV, raising=False)
    v = SessionVault()
    assert v.ephemeral_key is True
    assert v.stats()["ephemeral_key"] is True


def test_configured_key_is_used(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv(PRIMARY_KEY_ENV, key)
    v = SessionVault()
    assert v.ephemeral_key is False

    ph = v.next_placeholder("s1", "PAN")
    v.store("s1", ph, "ABCDE1234F")
    # the configured key alone must be able to read the stored ciphertext
    ciphertext = v._store["s1"][ph][0]
    assert Fernet(key.encode()).decrypt(ciphertext).decode() == "ABCDE1234F"


def test_invalid_key_fails_loudly(monkeypatch):
    monkeypatch.setenv(PRIMARY_KEY_ENV, "not-a-valid-fernet-key")
    with pytest.raises(RuntimeError, match="not a valid Fernet key"):
        SessionVault()


def test_retired_key_still_decrypts(monkeypatch):
    """The rotation path: tokens issued under the old key keep resolving."""
    old = Fernet.generate_key().decode()
    monkeypatch.setenv(PRIMARY_KEY_ENV, old)
    v1 = SessionVault()
    ph = v1.next_placeholder("s1", "AADHAAR")
    v1.store("s1", ph, AADHAAR)
    old_ciphertext = v1._store["s1"][ph]

    new = Fernet.generate_key().decode()
    monkeypatch.setenv(PRIMARY_KEY_ENV, new)
    monkeypatch.setenv(RETIRED_KEYS_ENV, old)
    v2 = SessionVault()
    v2._store["s1"][ph] = old_ciphertext          # simulate carried-over state

    assert v2.resolve_text("s1", ph) == AADHAAR
    assert v2.stats()["keys_loaded"] == 2


def test_rotate_reencrypts_existing_values():
    v = SessionVault()
    ph = v.next_placeholder("s1", "AADHAAR")
    v.store("s1", ph, AADHAAR)
    before = v._store["s1"][ph][0]

    v.rotate(Fernet.generate_key().decode())

    after = v._store["s1"][ph][0]
    assert before != after, "ciphertext unchanged after rotation"
    assert v.resolve_text("s1", ph) == AADHAAR, "value unreadable after rotation"


def test_entries_expire():
    """PII must not live in memory indefinitely."""
    v = SessionVault(ttl_seconds=1)
    ph = v.next_placeholder("s1", "AADHAAR")
    v.store("s1", ph, AADHAAR)
    assert v.resolve_text("s1", ph) == AADHAAR

    time.sleep(1.2)
    v.store("s2", v.next_placeholder("s2", "PAN"), "ABCDE1234F")  # triggers purge
    assert v.resolve_text("s1", ph) == ph, "expired entry still resolvable"
    assert v.stats()["entries"] == 1


def test_session_cap_is_enforced():
    v = SessionVault(max_sessions=5)
    for i in range(20):
        sid = f"s{i}"
        v.store(sid, v.next_placeholder(sid, "PAN"), "ABCDE1234F")
    assert v.stats()["sessions"] <= 5
