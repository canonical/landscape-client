import logging
import uuid

# exclude _get_machine_id
__all__ = [
    "get_namespaced_machine_id",
    "LANDSCAPE_CLIENT_APP_UUID",
    "MACHINE_ID_FILE",
    "MACHINE_ID_SIZE",
]

# Used to hash machine ids for client instances.
# It was generated using `uuidgen -r`
# This value should never change.
LANDSCAPE_CLIENT_APP_UUID = uuid.UUID("534a0cda-35a7-4f8a-a5cb-d8d9bb24a790")

# https://manpages.ubuntu.com/manpages/bionic/man5/machine-id.5.html
# We expect 32 ASCII characters, so we won't read in any more than
# the expected 32 bytes.
MACHINE_ID_FILE = "/etc/machine-id"
MACHINE_ID_SIZE = 32


def _get_machine_id() -> str:
    with open(MACHINE_ID_FILE, "r") as f:
        machine_id = f.read(MACHINE_ID_SIZE)
    return machine_id


def get_namespaced_machine_id() -> uuid.UUID | None:
    try:
        machine_id = _get_machine_id()
    except Exception as e:
        logging.warning(str(e))
        return None
    if not machine_id:
        return
    return uuid.uuid5(LANDSCAPE_CLIENT_APP_UUID, machine_id)
