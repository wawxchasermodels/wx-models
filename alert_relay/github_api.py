"""GitHub REST calls used by the heartbeat, secret upload, and sent-index publish.

Stdlib only. Tokens go in the Authorization header and are never logged.
Response bodies are returned to the caller; this module does not print them.
"""
import json
import urllib.error
import urllib.request

API = "https://api.github.com"


class GitHubError(Exception):
    def __init__(self, code, message):
        super().__init__("github http %s" % code)
        self.code = code
        self.message = message


def request(method, path, body=None, token="", timeout=30, accept="application/vnd.github+json"):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "wx-models-alert-relay",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as e:
        raw = e.read() if e.fp else b""
        status = e.code
    except urllib.error.URLError as e:
        raise GitHubError(0, type(e.reason).__name__ if getattr(e, "reason", None) else "URLError") from None
    text = raw.decode("utf-8", "replace") if raw else ""
    if accept == "application/vnd.github.raw":
        parsed = text
    else:
        try:
            parsed = json.loads(text) if text else None
        except Exception:
            parsed = {"message": text[:180]}
    return status, parsed


def upsert_variable(repo, name, value, token):
    code, _body = request("PATCH", "/repos/%s/actions/variables/%s" % (repo, name),
                          {"name": name, "value": value}, token=token)
    if code == 404:
        code, _body = request("POST", "/repos/%s/actions/variables" % repo,
                              {"name": name, "value": value}, token=token)
    return code


def get_public_key(repo, token):
    code, body = request("GET", "/repos/%s/actions/secrets/public-key" % repo, token=token)
    if code != 200 or not isinstance(body, dict):
        return None
    return body.get("key_id"), body.get("key")


def put_secret(repo, name, encrypted_b64, key_id, token):
    code, _body = request(
        "PUT",
        "/repos/%s/actions/secrets/%s" % (repo, name),
        {"encrypted_value": encrypted_b64, "key_id": key_id},
        token=token,
    )
    return code


def get_ref(repo, branch, token):
    return request("GET", "/repos/%s/git/ref/heads/%s" % (repo, branch), token=token)


def ensure_branch(repo, branch, from_branch, token):
    code, _body = get_ref(repo, branch, token)
    if code == 200:
        return True
    code, main = get_ref(repo, from_branch, token)
    if code != 200 or not isinstance(main, dict):
        return False
    sha = ((main.get("object") or {}).get("sha")) or ""
    if not sha:
        return False
    code, _body = request(
        "POST",
        "/repos/%s/git/refs" % repo,
        {"ref": "refs/heads/%s" % branch, "sha": sha},
        token=token,
    )
    return code in (201, 422)


def get_contents_sha(repo, path, ref, token):
    code, body = request("GET", "/repos/%s/contents/%s?ref=%s" % (repo, path, ref), token=token)
    if code == 200 and isinstance(body, dict):
        return body.get("sha")
    return None


def put_contents(repo, path, branch, message, content_bytes, sha, token):
    import base64
    body = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    return request("PUT", "/repos/%s/contents/%s" % (repo, path), body, token=token)


def get_raw_file(repo, path, ref, token=""):
    """Return (status, text). Public repos answer without a token."""
    return request(
        "GET",
        "/repos/%s/contents/%s?ref=%s" % (repo, path, ref),
        token=token,
        accept="application/vnd.github.raw",
    )
