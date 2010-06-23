import os

from landscape.patch import UpgradeManager
from landscape.lib.persist import Persist
from landscape.package.store import PackageStore


upgrade_manager = UpgradeManager()


def migrate_data_file(data_dir,
                      filename="data.bpickle",
                      broker_filename="broker.bpickle",
                      monitor_filename="monitor.bpickle",
                      hashdb_filename="hash.db",
                      sqlite_filename="hash.sqlite",
                      manager=upgrade_manager):
    """
    This function is triggered by the post-inst script when landscape
    is upgraded. It applies all the upgraders to the old monolithic
    persist data file and then splits the file up into multiple
    persist files for each new per-process service.
    """
    filename = os.path.join(data_dir, filename)
    broker_filename = os.path.join(data_dir, broker_filename)
    monitor_filename = os.path.join(data_dir, monitor_filename)
    hashdb_filename = os.path.join(data_dir, hashdb_filename)
    sqlite_filename = os.path.join(data_dir, sqlite_filename)

    # Make sure all the legacy upgraders up to this point have been
    # applied if an upgrade manager was passed in.
    persist = Persist(filename=filename)
    if os.path.exists(filename):
        manager.apply(persist)
    else:
        manager.initialize(persist)
    persist.save()

    # Migrate broker data.
    broker_persist = Persist(filename=broker_filename)
    broker_persist.set("message-store", persist.get("message-store"))
    broker_persist.set("message-exchange", persist.get("message-exchange"))
    broker_persist.set("registration", persist.get("registration"))
    broker_persist.save()

    # Migrate monitor data.
    monitor_persist = Persist(filename=monitor_filename)
    for plugin in ["client-uptime", "computer-uptime", "computer-info",
                   "load-average", "memory-info", "mount-info",
                   "processor-info", "temperature", "hardware-inventory",
                   "users"]:
        if persist.has(plugin):
            monitor_persist.set(plugin, persist.get(plugin))
    monitor_persist.save()

    # package data needs to be migrated to a sqlite db
    if os.path.exists(hashdb_filename):
        import gdbm
        hashdb = gdbm.open(hashdb_filename, "r")
        store = PackageStore(sqlite_filename)

        hash_ids = {}
        key = hashdb.firstkey()
        while key is not None:
            try:
                hash = hashdb[key]
                hash_ids[hash] = int(key)
            except ValueError:
                pass
            key = hashdb.nextkey(key)

        store.set_hash_ids(hash_ids)
        store.add_installed(persist.get("package.installed", ()))
        store.add_available(persist.get("package.available", ()))
        store.add_available_upgrades(
            persist.get("package.available_upgrades", ()))


@upgrade_manager.upgrader(8)
def index_users_on_names_added(persist):
    """
    Upgrade from persisted stores indexed on uid/gid to username/groupname.
    """
    old_user_data = persist.get("users")
    new_user_data = {}
    new_group_data = {}

    if old_user_data.get("users"):
        for (userid, user_data) in old_user_data.get("users").iteritems():
            new_user_data[user_data["username"]] = user_data

    if old_user_data.get("groups"):
        for (groupid, group_data) in old_user_data.get("groups").iteritems():
            old_group_members = group_data["members"]
            new_group_members = []
            for user_id in old_group_members:
                # If an admin leaves a username in a list of user members who
                # has been deleted, we can probably safely ignore it.
                username = old_user_data.get("users").get(
                    user_id, {}).get("username")
                if username:
                    new_group_members.append(username)
            group_data["members"] = sorted(new_group_members)
            new_group_data[group_data["name"]] = group_data

    persist.set("users", {"users": new_user_data, "groups": new_group_data})


@upgrade_manager.upgrader(7)
def move_registration_data(persist):
    """Move registration-related information to a sensible place."""
    persist.move("message-store.secure_id", "registration.secure-id")
    persist.move("http-ping.insecure-id", "registration.insecure-id")


@upgrade_manager.upgrader(6)
def rename_message_queue(persist):
    """Rename "message-queue" to "message-store", if necessary."""
    persist.move("message-queue", "message-store")


@upgrade_manager.upgrader(5)
def user_change_detection_added(persist):
    """
    The user and group plugin has been refactored to include detecting
    and reporting changes made externally to Landscape.  Old data
    needs to be wiped out so that the plugin sends fresh data to the
    server.
    """
    persist.remove(("users", "users"))
    persist.remove(("users", "groups"))


@upgrade_manager.upgrader(4)
def group_support_added(persist):
    """
    The 'users' data used to be stored at /users/data, but now it is
    in /users/users, next to /users/groups. The key will be created
    automatically, but the old location will be deleted to prevent
    cruft from accumulating.
    """
    persist.remove(("users", "data"))


@upgrade_manager.upgrader(3)
def delete_urgent_exchange(persist):
    """
    Urgent exchange is now in-memory only.
    """
    persist.remove("message-exchange.urgent-exchange")


@upgrade_manager.upgrader(2)
def delete_old_resource_data(persist):
    """
    The accumulation logic in the client has been refactored.  The
    previous logic required the mount info plugin to persist last
    known values.  The new logic doesn't required the plugin to worry
    about this detail, so we can remove old persisted values.

    Also, some keys for persisted information have changed, so stored
    information is being reset.
    """
    persist.remove("load-average")
    persist.remove("memory-info")
    persist.remove("mount-info")
    persist.remove("processor-info")
    persist.remove("temperature")
    persist.remove("trip-points")


@upgrade_manager.upgrader(1)
def delete_user_data(persist):
    """
    The client was released with user support before the server was
    deployed; the client tried sending messages about user data and
    the server ignored it. Unfortunately, the client didn't know they
    were ignored, so it's not sending new data.
    """
    persist.remove(("users", "data"))
