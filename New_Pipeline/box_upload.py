"""Push sweep results (PDF/CSV/XLSX) to a Box folder via a Client Credentials Grant (CCG) app.

Enabled with ``python -m New_Pipeline.sweep --box``. Needs a Box Custom App (Box
Developer Console -> Create New App -> Custom App -> authentication method "Client
Credentials Grant") and three env vars read from it:

    BOX_CLIENT_ID          -- app's Client ID (Configuration tab)
    BOX_CLIENT_SECRET       -- app's Client Secret (Configuration tab)
    BOX_ENTERPRISE_ID       -- your Box enterprise ID (Configuration tab); this is what
                              makes the CCG token authenticate as the app's own service
                              account rather than as a specific managed user

The service account has its own email and starts with access to nothing. It must be
invited as a **collaborator (Editor)** on the destination folder --
https://imperialcollegelondon.app.box.com/folder/412794290360 -- the same way you'd
invite any other person, or every upload here will 404 looking for that folder. Find
its login by calling ``client.users.get_user_me().login`` once auth works (see the
module's ``_client()`` below).

The app must also be **authorized** by a Box admin (Admin Console -> Apps -> Custom
Apps Manager, using the app's Client ID) before the first call works -- Box calls this
step out separately from creating the app itself; skipping it fails with
``invalid_grant: App is not yet authorized for use``.

Target folder defaults to the ID above; override with BOX_FOLDER_ID if you ever want to
send a particular sweep's results somewhere else.

Uses ``box_sdk_gen`` (Box's current generated SDK -- what the ``boxsdk`` PyPI package
now ships, as of 10.x; its API is unrelated to the older ``boxsdk`` v2/v3 interface of
the same name), not the legacy ``boxsdk`` client classes.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_FOLDER_ID = "412794290360"


def _client():
    from box_sdk_gen import BoxCCGAuth, BoxClient, CCGConfig

    missing = [v for v in ("BOX_CLIENT_ID", "BOX_CLIENT_SECRET", "BOX_ENTERPRISE_ID")
               if not os.environ.get(v)]
    if missing:
        raise RuntimeError(f"missing env var(s) for Box auth: {', '.join(missing)}")

    config = CCGConfig(
        client_id=os.environ["BOX_CLIENT_ID"],
        client_secret=os.environ["BOX_CLIENT_SECRET"],
        enterprise_id=os.environ["BOX_ENTERPRISE_ID"],
    )
    return BoxClient(auth=BoxCCGAuth(config))


def upload_file(path: Path, folder_id: str | None = None) -> str:
    """Upload ``path`` into the Box folder, or push a new version if a file with the
    same name is already there. Returns the Box file ID."""
    from box_sdk_gen import (
        UploadFileAttributes,
        UploadFileAttributesParentField,
        UploadFileVersionAttributes,
    )

    client = _client()
    folder_id = folder_id or os.environ.get("BOX_FOLDER_ID", DEFAULT_FOLDER_ID)

    items = client.folders.get_folder_items(folder_id).entries
    existing = {item.name: item for item in items
                if getattr(item.type, "value", item.type) == "file"}

    with open(path, "rb") as fh:
        if path.name in existing:
            result = client.uploads.upload_file_version(
                existing[path.name].id,
                UploadFileVersionAttributes(name=path.name),
                fh,
            )
            action = "updated (new version)"
        else:
            result = client.uploads.upload_file(
                UploadFileAttributes(
                    name=path.name,
                    parent=UploadFileAttributesParentField(id=folder_id),
                ),
                fh,
            )
            action = "uploaded"

    file_id = result.entries[0].id
    print(f"[box] {action} {path.name} -> file {file_id}")
    return file_id


def upload_sweep_results(paths: dict, folder_id: str | None = None) -> None:
    """Push results.pdf/csv/xlsx (whichever exist) to the Box folder.

    Never raises -- a Box outage, an unauthorized app, or an expired/missing credential
    should log and move on, not take the sweep's exit status down with it.
    """
    for key in ("pdf", "csv", "xlsx"):
        p = paths.get(key)
        if not p or not Path(p).exists():
            continue
        try:
            upload_file(Path(p), folder_id)
        except Exception as exc:                                  # noqa: BLE001
            print(f"[box] upload of {Path(p).name} failed: {type(exc).__name__}: {exc}")
