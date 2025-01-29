import os

from landscape import VERSION
from landscape.client import GROUP
from landscape.client import USER
from landscape.lib.fetch import fetch_async
from landscape.lib.persist import Persist


async def save_attachments(
    config,
    attachments,
    dest,
    uid=None,
    gid=None,
) -> None:
    """Downloads `attachments` from Landscape Server, writing them to `dest`.

    :param config: The Landscape Client configuration.
    :param attachments: The names and IDs of the attachments to download, an
        iterable of pairs.
    :param dest: The directory to write the downloaded attachments to.
    :param uid: The user who should own the files.
    :param gid: The group that should own the files.

    :raises HTTPCodeError: If Server responds with an error HTTP code.
    """
    root_path = config.url.rsplit("/", 1)[0] + "/attachment/"
    headers = {
        "User-Agent": "landscape-client/" + VERSION,
        "Content-Type": "application/octet-stream",
        "X-Computer-ID": _get_secure_id(config),
    }

    for filename, attachment_id in attachments:
        if isinstance(attachment_id, str):
            # Backward-compatibility with inline attachments.
            data = attachment_id.encode()
        else:
            data = await fetch_async(
                root_path + str(attachment_id),
                cainfo=config.ssl_public_key,
                headers=headers,
            )

        full_filename = os.path.join(dest, filename)
        with open(full_filename, "wb") as attachment:
            attachment.write(data)

        os.chmod(full_filename, 0o600)
        if uid is not None:
            os.chown(full_filename, uid, gid)


def _get_secure_id(config) -> str:
    """Retrieves the secure ID from the broker persistent storage."""
    persist = Persist(
        filename=os.path.join(config.data_path, "broker.bpickle"),
        user=USER,
        group=GROUP,
    )

    secure_id = persist.root_at("registration").get("secure-id")
    secure_id = secure_id.decode("ascii")

    return secure_id
