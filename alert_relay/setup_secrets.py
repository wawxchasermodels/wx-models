#!/usr/bin/env python3
"""Upload the four webhook secrets from the box environment into Actions secrets.

Run ONCE on the box. Stdlib plus PyNaCl (libsodium sealed box, which is the
format the Actions secrets API expects).

  python3 -m pip install --user pynacl
  # env already has the four webhook values plus GITHUB_RELAY_TOKEN
  python3 setup_secrets.py

Prints only the variable name, the length of the value, and OK or FAIL.
Values are never printed, logged, or written to disk by this script.

Env:
  GITHUB_RELAY_TOKEN   fine-grained PAT, this repo only, Secrets: Read and write
  GITHUB_REPOSITORY    optional, default wawxchasermodels/wx-models
  URGENT_WEBHOOK_URL, URGENT_WEBHOOK_AUTH, QUIET_WEBHOOK_URL, QUIET_WEBHOOK_AUTH
"""
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import constants
import github_api

try:
    from nacl.public import PublicKey, SealedBox
except Exception:
    PublicKey = SealedBox = None


def seal(public_b64, plaintext):
    key = PublicKey(base64.b64decode(public_b64))
    encrypted = SealedBox(key).encrypt(plaintext.encode("utf-8"))
    return base64.b64encode(encrypted).decode("ascii")


def _repo():
    return os.environ.get("GITHUB_REPOSITORY") or os.environ.get("ALERT_RELAY_REPO") or constants.DEFAULT_REPO


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        sys.stderr.write(__doc__.strip() + "\n")
        return 0
    if PublicKey is None:
        print("pynacl FAIL missing")
        return 1
    token = os.environ.get("GITHUB_RELAY_TOKEN") or ""
    if not token:
        print("GITHUB_RELAY_TOKEN len=0 FAIL missing")
        return 1
    got = github_api.get_public_key(_repo(), token)
    if not got or not got[0] or not got[1]:
        print("public-key len=0 FAIL")
        return 1
    key_id, public = got
    failed = False
    for name in constants.SECRET_NAMES:
        value = os.environ.get(name) or ""
        if not value:
            print("%s len=0 FAIL missing" % name)
            failed = True
            continue
        try:
            encrypted = seal(public, value)
            code = github_api.put_secret(_repo(), name, encrypted, key_id, token)
        except Exception as exc:
            print("%s len=%d FAIL %s" % (name, len(value), type(exc).__name__))
            failed = True
            continue
        if code in (201, 204):
            print("%s len=%d OK" % (name, len(value)))
        else:
            print("%s len=%d FAIL http %s" % (name, len(value), code))
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
