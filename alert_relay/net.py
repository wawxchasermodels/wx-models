"""Small urllib stand-in for the requests.Session calls the watchers make.

The copied filters call session.get/post(..., headers=, timeout=) and then
status_code, json(), text, content, and raise_for_status(). Timeouts and
connection errors propagate so the watchers' existing retry paths handle them.
"""
import json
import urllib.error
import urllib.request


class HTTPError(Exception):
    def __init__(self, code):
        super().__init__("HTTP %s" % code)
        self.code = code


class Response:
    def __init__(self, status, content):
        self.status_code = status
        self.content = content or b""
        self.text = self.content.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.content.decode("utf-8"))

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise HTTPError(self.status_code)


class Session:
    def get(self, url, headers=None, timeout=30):
        return self._req("GET", url, headers=headers, timeout=timeout)

    def post(self, url, json=None, headers=None, timeout=30):
        headers = dict(headers or {})
        body = None
        if json is not None:
            body = __import__("json").dumps(json).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        return self._req("POST", url, body=body, headers=headers, timeout=timeout)

    def _req(self, method, url, body=None, headers=None, timeout=30):
        req = urllib.request.Request(url, data=body, headers=dict(headers or {}), method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return Response(getattr(resp, "status", 200), resp.read())
        except urllib.error.HTTPError as e:
            payload = e.read() if e.fp else b""
            return Response(e.code, payload)
