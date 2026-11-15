# Local-preview shim (11-14): /workspace/qa_realpreview_20261031/qa.py is missing on the box. For a localhost preview no
# extra request headers are needed, so add_hdr just lets the request through. Not used for production guard runs.
async def add_hdr(route, request=None):
    await route.continue_()
