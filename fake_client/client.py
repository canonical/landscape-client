"""Fake Landscape Client for load testing.

A lightweight async client that mimics the Landscape Client protocol,
allowing 10,000+ simultaneous fake clients to register and exchange
messages with a Landscape Server.

Uses aiohttp for async HTTP and the real bpickle serialization from
the landscape-client codebase.
"""

import asyncio
import hashlib
import logging
import os
import random
import socket
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import aiohttp

# Add the repo root to sys.path so we can import landscape.lib.bpickle
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from landscape import CLIENT_API, SERVER_API, VERSION  # noqa: E402
from landscape.lib import bpickle  # noqa: E402

from .packages import (  # noqa: E402
    SERIES_PACKAGES,
    get_available_upgrade_ids,
    get_package_hashes,
    get_package_ids,
    get_security_upgrade_ids,
)

logger = logging.getLogger("fake_client")

# Realistic hardware models for random selection
HARDWARE_MODELS = [
    "Dell PowerEdge R640",
    "Dell PowerEdge R740",
    "HP ProLiant DL360 Gen10",
    "HP ProLiant DL380 Gen10",
    "Lenovo ThinkSystem SR630",
    "Lenovo ThinkSystem SR650",
    "Supermicro SYS-6019U-TRT",
    "Dell OptiPlex 7090",
    "HP EliteDesk 800 G8",
    "Lenovo ThinkCentre M920",
    "QEMU Standard PC (Q35 + ICH9, 2009)",
    "QEMU Standard PC (i440FX + PIIX, 1996)",
]

CPU_MODELS = [
    "Intel(R) Xeon(R) Gold 6248 CPU @ 2.50GHz",
    "Intel(R) Xeon(R) Silver 4214 CPU @ 2.20GHz",
    "Intel(R) Xeon(R) Platinum 8280 CPU @ 2.70GHz",
    "Intel(R) Core(TM) i7-10700 CPU @ 2.90GHz",
    "Intel(R) Core(TM) i9-11900K @ 3.50GHz",
    "AMD EPYC 7742 64-Core Processor",
    "AMD EPYC 7R13 48-Core Processor",
    "AMD Ryzen 9 5950X 16-Core Processor",
    "Intel(R) Xeon(R) E-2288G CPU @ 3.70GHz",
    "Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz",
]

SERIES_LIST = ["focal", "jammy", "noble", "resolute"]


@dataclass
class FakeClientState:
    """State for a single fake client instance."""

    client_id: int
    series: str
    computer_title: str
    hostname: str
    machine_id: str

    # Server-assigned after registration
    secure_id: str | None = None
    insecure_id: int | None = None
    server_uuid: bytes | None = None
    exchange_token: bytes | None = None

    # Message sequencing
    sequence: int = 0
    next_expected_sequence: int = 0
    accepted_types_hash: bytes = b""

    # Hardware profile (randomized once)
    total_memory: int = 0
    total_swap: int = 0
    cpu_model: str = ""
    hardware_model: str = ""
    num_cpus: int = 1

    # Package state
    installed_package_ids: list[int] = field(default_factory=list)
    available_upgrade_ids: list[int] = field(default_factory=list)
    security_upgrade_ids: list[int] = field(default_factory=list)

    # Track what we've sent
    registered: bool = False
    sent_initial_info: bool = False
    sent_packages: bool = False
    exchange_count: int = 0


def _generate_client_state(client_id: int) -> FakeClientState:
    """Generate a deterministic but realistic client state."""
    rng = random.Random(client_id)

    series = SERIES_LIST[client_id % len(SERIES_LIST)]
    hostname = f"fake-{series}-{client_id:05d}.example.com"
    computer_title = f"Fake {series.capitalize()} Client {client_id}"
    machine_id = hashlib.sha256(
        f"fake-machine-{client_id}".encode(),
    ).hexdigest()

    # Randomize hardware
    memory_options = [
        2 * 1024**3,
        4 * 1024**3,
        8 * 1024**3,
        16 * 1024**3,
        32 * 1024**3,
        64 * 1024**3,
    ]
    swap_options = [0, 1 * 1024**3, 2 * 1024**3, 4 * 1024**3, 8 * 1024**3]
    cpu_count_options = [1, 2, 4, 8, 16, 32, 64]

    installed_ids = get_package_ids(series, seed=client_id)
    num_upgrades = rng.randint(0, 15)
    upgrade_ids = get_available_upgrade_ids(
        installed_ids,
        count=num_upgrades,
        seed=client_id,
    )
    num_security = rng.randint(0, min(5, len(upgrade_ids)))
    sec_ids = get_security_upgrade_ids(
        upgrade_ids,
        count=num_security,
        seed=client_id,
    )

    return FakeClientState(
        client_id=client_id,
        series=series,
        computer_title=computer_title,
        hostname=hostname,
        machine_id=machine_id,
        total_memory=rng.choice(memory_options),
        total_swap=rng.choice(swap_options),
        cpu_model=rng.choice(CPU_MODELS),
        hardware_model=rng.choice(HARDWARE_MODELS),
        num_cpus=rng.choice(cpu_count_options),
        installed_package_ids=installed_ids,
        available_upgrade_ids=upgrade_ids,
        security_upgrade_ids=sec_ids,
    )


def _build_registration_payload(
    state: FakeClientState,
    account_name: str,
    registration_key: str | None,
) -> dict:
    """Build the registration message payload."""
    message: dict[str, Any] = {
        "type": "register",
        "computer_title": state.computer_title,
        "account_name": account_name,
        "hostname": state.hostname,
        "machine_id": state.machine_id,
        "vm_info": b"kvm",
        "container_info": "",
        "ubuntu_pro_info": "{}",
    }
    if registration_key:
        message["registration_password"] = registration_key

    return {"messages": [message]}


def _build_computer_info_message(state: FakeClientState) -> dict:
    """Build computer-info message with realistic system data."""
    return {
        "type": "computer-info",
        "hostname": state.hostname,
        "total-memory": state.total_memory // 1024,  # KB
        "total-swap": state.total_swap // 1024,  # KB
        "timestamp": int(time.time()),
    }


def _build_distribution_info_message(state: FakeClientState) -> dict:
    """Build distribution-info message."""
    series_data = SERIES_PACKAGES[state.series]
    return {
        "type": "distribution-info",
        "distributor-id": "Ubuntu",
        "description": series_data["description"],
        "release": series_data["release"],
        "code-name": series_data["codename"],
        "timestamp": int(time.time()),
    }


def _build_processor_info_message(state: FakeClientState) -> list[dict]:
    """Build processor-info message."""
    processors = []
    for i in range(state.num_cpus):
        processors.append(
            {
                "processor-id": i,
                "vendor": state.cpu_model.split()[0],
                "model": state.cpu_model,
                "cache-size": random.choice([256, 512, 1024, 2048, 4096]),
            }
        )
    return [
        {
            "type": "processor-info",
            "processors": processors,
            "timestamp": int(time.time()),
        }
    ]


def _build_load_average_message(state: FakeClientState) -> dict:
    """Build load-average message with realistic random values."""
    rng = random.Random(state.client_id + int(time.time() / 60))
    base_load = rng.uniform(0.01, 2.0)
    return {
        "type": "load-average",
        "load-averages": [
            (int(time.time()), round(base_load, 2)),
            (int(time.time()), round(base_load * 1.1, 2)),
            (int(time.time()), round(base_load * 0.9, 2)),
        ],
        "timestamp": int(time.time()),
    }


def _build_memory_info_message(state: FakeClientState) -> dict:
    """Build memory-info message with realistic values."""
    rng = random.Random(state.client_id + int(time.time() / 60))
    total_kb = state.total_memory // 1024
    used_pct = rng.uniform(0.15, 0.85)
    free_kb = int(total_kb * (1 - used_pct))
    buffers_kb = int(total_kb * rng.uniform(0.01, 0.05))
    cached_kb = int(total_kb * rng.uniform(0.10, 0.40))

    swap_total_kb = state.total_swap // 1024
    swap_used_kb = int(swap_total_kb * rng.uniform(0, 0.2))

    return {
        "type": "memory-info",
        "memory-info": [
            (
                int(time.time()),
                total_kb,
                free_kb,
                buffers_kb + cached_kb,
            ),
        ],
        "swap-info": [
            (int(time.time()), swap_total_kb, swap_used_kb),
        ],
        "timestamp": int(time.time()),
    }


def _build_mount_info_message(state: FakeClientState) -> dict:
    """Build mount-info message."""
    rng = random.Random(state.client_id + int(time.time() / 300))
    total_gb = rng.choice([20, 40, 80, 100, 200, 500, 1000])
    total_kb = total_gb * 1024 * 1024
    used_pct = rng.uniform(0.10, 0.75)

    return {
        "type": "mount-info",
        "mount-info": [
            {
                "mount-point": "/",
                "device": "/dev/sda1",
                "filesystem": "ext4",
                "total-space": total_kb,
                "free-space": int(total_kb * (1 - used_pct)),
            },
            {
                "mount-point": "/boot",
                "device": "/dev/sda2",
                "filesystem": "ext4",
                "total-space": 1024 * 1024,  # 1GB
                "free-space": int(1024 * 1024 * rng.uniform(0.5, 0.9)),
            },
        ],
        "timestamp": int(time.time()),
    }


def _build_packages_message(state: FakeClientState) -> dict:
    """Build packages message with installed, available, upgrades."""
    return {
        "type": "packages",
        "installed": state.installed_package_ids,
        "available": state.installed_package_ids,
        "available-upgrades": state.available_upgrade_ids,
        "security": state.security_upgrade_ids,
        "locked": [],
        "autoremovable": [],
        "not-installed": [],
        "not-available": [],
        "timestamp": int(time.time()),
    }


def _build_reboot_required_message(state: FakeClientState) -> dict:
    """Build reboot-required message."""
    rng = random.Random(state.client_id + int(time.time() / 3600))
    return {
        "type": "reboot-required-info",
        "flag": rng.random() < 0.1,  # 10% chance of needing reboot
        "timestamp": int(time.time()),
    }


def _build_cpu_usage_message(state: FakeClientState) -> dict:
    """Build cpu-usage message."""
    rng = random.Random(state.client_id + int(time.time() / 60))
    return {
        "type": "cpu-usage",
        "cpu-usages": [
            (int(time.time()), round(rng.uniform(0.5, 95.0), 1)),
        ],
        "timestamp": int(time.time()),
    }


def _build_initial_messages(state: FakeClientState) -> list[dict]:
    """Build the initial set of messages sent after registration."""
    msgs: list[dict] = []
    msgs.append(_build_computer_info_message(state))
    msgs.append(_build_distribution_info_message(state))
    msgs.extend(_build_processor_info_message(state))
    msgs.append(_build_load_average_message(state))
    msgs.append(_build_memory_info_message(state))
    msgs.append(_build_mount_info_message(state))
    msgs.append(_build_reboot_required_message(state))
    msgs.append(_build_cpu_usage_message(state))
    return msgs


def _build_periodic_messages(state: FakeClientState) -> list[dict]:
    """Build messages for a periodic exchange (after initial)."""
    rng = random.Random(state.client_id + int(time.time()))
    msgs: list[dict] = []

    # Always send load average and CPU usage
    msgs.append(_build_load_average_message(state))
    msgs.append(_build_cpu_usage_message(state))

    # Periodically send memory info (~50% of exchanges)
    if rng.random() < 0.5:
        msgs.append(_build_memory_info_message(state))

    # Occasionally send mount info (~20% of exchanges)
    if rng.random() < 0.2:
        msgs.append(_build_mount_info_message(state))

    # Rarely send reboot-required (~5% of exchanges)
    if rng.random() < 0.05:
        msgs.append(_build_reboot_required_message(state))

    return msgs


def _build_exchange_payload(
    state: FakeClientState,
    messages: list[dict],
) -> dict:
    """Build a full exchange payload."""
    # Apply API and sequence to each message
    for msg in messages:
        if "api" not in msg:
            msg["api"] = SERVER_API
        if "timestamp" not in msg:
            msg["timestamp"] = int(time.time())

    payload = {
        "server-api": SERVER_API,
        "client-api": CLIENT_API,
        "sequence": state.sequence,
        "accepted-types": state.accepted_types_hash,
        "messages": messages,
        "total-messages": len(messages),
        "next-expected-sequence": state.next_expected_sequence,
    }
    return payload


def _handle_activity_message(
    state: FakeClientState,
    message: dict,
) -> dict | None:
    """Handle an incoming server activity message and produce a response.

    Returns a response message or None if no response is needed.
    """
    rng = random.Random(state.client_id + int(time.time()))
    msg_type = message.get("type", "")

    if msg_type in ("change-packages", "change-packages-result"):
        op_id = message.get("operation-id")
        if op_id is not None:
            # Simulate success (90%), failure (10%)
            success = rng.random() < 0.9
            return {
                "type": "operation-result",
                "operation-id": op_id,
                "status": 0 if success else 1,
                "result-code": 0 if success else 100,
                "result-text": (
                    "Package changes applied successfully."
                    if success
                    else "E: Unable to locate package fake-missing-pkg"
                ),
                "timestamp": int(time.time()),
            }

    elif msg_type == "run-script":
        op_id = message.get("operation-id")
        if op_id is not None:
            exit_code = rng.choice([0, 0, 0, 0, 1, 2, 127])
            return {
                "type": "operation-result",
                "operation-id": op_id,
                "status": 0 if exit_code == 0 else 1,
                "result-code": exit_code,
                "result-text": (
                    "Script executed successfully."
                    if exit_code == 0
                    else f"Script exited with code {exit_code}"
                ),
                "timestamp": int(time.time()),
            }

    elif msg_type == "shutdown":
        op_id = message.get("operation-id")
        if op_id is not None:
            return {
                "type": "operation-result",
                "operation-id": op_id,
                "status": 0,
                "result-code": 0,
                "result-text": "Shutdown requested (fake client, ignoring).",
                "timestamp": int(time.time()),
            }

    elif msg_type == "resynchronize":
        # Trigger re-send of all info on next exchange
        state.sent_initial_info = False
        state.sent_packages = False

    elif msg_type == "accepted-types":
        types = message.get("types", [])
        h = hashlib.md5(  # noqa: S324
            b";".join(sorted(t.encode() for t in types)),
        ).digest()
        state.accepted_types_hash = h

    elif msg_type == "set-intervals":
        # Acknowledge but we manage our own intervals
        pass

    return None


async def _do_http_exchange(
    session: aiohttp.ClientSession,
    url: str,
    payload: dict,
    computer_id: str | None = None,
    exchange_token: bytes | None = None,
    ssl_cert: str | None = None,
) -> dict | None:
    """Perform a single HTTP exchange with the server."""
    data = bpickle.dumps(payload)

    headers = {
        "X-Message-API": SERVER_API.decode(),
        "User-Agent": f"landscape-client/{VERSION}",
        "Content-Type": "application/octet-stream",
    }

    if computer_id:
        headers["X-Computer-ID"] = computer_id
    if exchange_token:
        headers["X-Exchange-Token"] = exchange_token.decode()

    ssl_context = None
    if ssl_cert:
        import ssl

        ssl_context = ssl.create_default_context(cafile=ssl_cert)

    try:
        async with session.post(
            url,
            data=data,
            headers=headers,
            ssl=ssl_context,
        ) as resp:
            if resp.status != 200:
                logger.warning(
                    "Client exchange got HTTP %d",
                    resp.status,
                )
                return None
            response_bytes = await resp.read()
    except Exception:
        logger.debug("Exchange failed", exc_info=True)
        return None

    try:
        return bpickle.loads(response_bytes)
    except Exception:
        logger.warning("Failed to decode server response")
        return None


async def run_fake_client(
    client_id: int,
    server_url: str,
    account_name: str,
    registration_key: str | None = None,
    exchange_interval: float = 900.0,
    ssl_cert: str | None = None,
    session: aiohttp.ClientSession | None = None,
    started_event: asyncio.Event | None = None,
):
    """Run a single fake client lifecycle.

    1. Register with the server
    2. Send initial system information
    3. Periodically exchange messages

    Args:
        client_id: Unique integer ID for this client.
        server_url: The Landscape server message-system URL.
        account_name: The Landscape account name.
        registration_key: Optional registration key/password.
        exchange_interval: Seconds between exchanges (default 900).
        ssl_cert: Path to SSL CA certificate for HTTPS verification.
        session: Shared aiohttp session for connection pooling.
        started_event: Event to signal this client has started.
    """
    state = _generate_client_state(client_id)
    own_session = session is None

    if own_session:
        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        session = aiohttp.ClientSession(timeout=timeout)

    try:
        # --- Phase 1: Registration ---
        reg_payload = _build_registration_payload(
            state,
            account_name,
            registration_key,
        )

        for attempt in range(5):
            result = await _do_http_exchange(
                session,
                server_url,
                reg_payload,
                ssl_cert=ssl_cert,
            )

            if result and "messages" in result:
                for msg in result["messages"]:
                    if msg.get("type") == "set-id":
                        state.secure_id = msg["id"]
                        state.insecure_id = msg["insecure-id"]
                        state.registered = True
                        break
                    elif msg.get("type") == "registration":
                        info = msg.get("info", "")
                        if info in ("unknown-account", "max-pending-computers"):
                            logger.error(
                                "Client %d registration failed: %s",
                                client_id,
                                info,
                            )
                            return

                if state.registered:
                    state.server_uuid = result.get("server-uuid")
                    state.exchange_token = result.get("next-exchange-token")
                    logger.info(
                        "Client %d registered (secure_id=%s)",
                        client_id,
                        state.secure_id[:16] if state.secure_id else "?",
                    )
                    break

            backoff = (2**attempt) + random.uniform(0, 1)
            logger.debug(
                "Client %d registration attempt %d failed, retrying in %.1fs",
                client_id,
                attempt + 1,
                backoff,
            )
            await asyncio.sleep(backoff)

        if not state.registered:
            logger.error(
                "Client %d failed to register after 5 attempts",
                client_id,
            )
            return

        if started_event:
            started_event.set()

        # --- Phase 2: Initial info exchange ---
        initial_msgs = _build_initial_messages(state)
        initial_msgs.append(_build_packages_message(state))
        payload = _build_exchange_payload(state, initial_msgs)
        state.sequence += len(initial_msgs)

        result = await _do_http_exchange(
            session,
            server_url,
            payload,
            computer_id=state.secure_id,
            exchange_token=state.exchange_token,
            ssl_cert=ssl_cert,
        )

        if result:
            state.exchange_token = result.get("next-exchange-token")
            if result.get("next-expected-sequence") is not None:
                state.next_expected_sequence = result[
                    "next-expected-sequence"
                ]
            state.sent_initial_info = True
            state.sent_packages = True
            state.exchange_count += 1

            # Handle any server messages
            for msg in result.get("messages", []):
                _handle_activity_message(state, msg)

        # --- Phase 3: Periodic exchanges ---
        while True:
            # Stagger exchanges to avoid thundering herd
            jitter = random.uniform(0, exchange_interval * 0.1)
            await asyncio.sleep(exchange_interval + jitter)

            messages = _build_periodic_messages(state)

            # If server requested resync, re-send everything
            if not state.sent_initial_info:
                messages = _build_initial_messages(state)
                state.sent_initial_info = True
            if not state.sent_packages:
                messages.append(_build_packages_message(state))
                state.sent_packages = True

            payload = _build_exchange_payload(state, messages)
            state.sequence += len(messages)

            result = await _do_http_exchange(
                session,
                server_url,
                payload,
                computer_id=state.secure_id,
                exchange_token=state.exchange_token,
                ssl_cert=ssl_cert,
            )

            if result:
                state.exchange_token = result.get("next-exchange-token")
                if result.get("next-expected-sequence") is not None:
                    state.next_expected_sequence = result[
                        "next-expected-sequence"
                    ]
                state.exchange_count += 1

                # Handle server messages and queue responses
                response_msgs: list[dict] = []
                for msg in result.get("messages", []):
                    resp = _handle_activity_message(state, msg)
                    if resp:
                        response_msgs.append(resp)

                # Send activity responses immediately if any
                if response_msgs:
                    resp_payload = _build_exchange_payload(
                        state,
                        response_msgs,
                    )
                    state.sequence += len(response_msgs)
                    resp_result = await _do_http_exchange(
                        session,
                        server_url,
                        resp_payload,
                        computer_id=state.secure_id,
                        exchange_token=state.exchange_token,
                        ssl_cert=ssl_cert,
                    )
                    if resp_result:
                        state.exchange_token = resp_result.get(
                            "next-exchange-token",
                        )
                        state.exchange_count += 1

                if state.exchange_count % 100 == 0:
                    logger.info(
                        "Client %d: %d exchanges completed",
                        client_id,
                        state.exchange_count,
                    )
            else:
                logger.debug(
                    "Client %d exchange failed, will retry next interval",
                    client_id,
                )

    except asyncio.CancelledError:
        logger.debug("Client %d cancelled", client_id)
    except Exception:
        logger.exception("Client %d encountered an error", client_id)
    finally:
        if own_session:
            await session.close()


async def run_many_clients(
    num_clients: int,
    server_url: str,
    account_name: str,
    registration_key: str | None = None,
    exchange_interval: float = 900.0,
    ssl_cert: str | None = None,
    batch_size: int = 100,
    batch_delay: float = 1.0,
):
    """Run many fake clients concurrently.

    Clients are started in batches to avoid overwhelming the server
    with simultaneous registration requests.

    Args:
        num_clients: Total number of fake clients to run.
        server_url: The Landscape server message-system URL.
        account_name: The Landscape account name.
        registration_key: Optional registration key/password.
        exchange_interval: Seconds between exchanges per client.
        ssl_cert: Path to SSL CA certificate.
        batch_size: Number of clients to start per batch.
        batch_delay: Seconds between batches.
    """
    # Use a single shared connection pool with generous limits
    connector = aiohttp.TCPConnector(
        limit=200,  # Max simultaneous connections
        limit_per_host=100,
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
    )
    timeout = aiohttp.ClientTimeout(total=120, connect=30)
    session = aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
    )

    tasks: list[asyncio.Task] = []
    registered_count = 0
    failed_count = 0

    logger.info(
        "Starting %d fake clients against %s (account: %s)",
        num_clients,
        server_url,
        account_name,
    )
    logger.info(
        "Exchange interval: %.0fs, batch size: %d, batch delay: %.1fs",
        exchange_interval,
        batch_size,
        batch_delay,
    )

    start_time = time.time()

    try:
        for batch_start in range(0, num_clients, batch_size):
            batch_end = min(batch_start + batch_size, num_clients)
            batch_events: list[asyncio.Event] = []

            for client_id in range(batch_start, batch_end):
                event = asyncio.Event()
                batch_events.append(event)
                task = asyncio.create_task(
                    run_fake_client(
                        client_id=client_id,
                        server_url=server_url,
                        account_name=account_name,
                        registration_key=registration_key,
                        exchange_interval=exchange_interval,
                        ssl_cert=ssl_cert,
                        session=session,
                        started_event=event,
                    ),
                    name=f"fake-client-{client_id}",
                )
                tasks.append(task)

            # Wait briefly for this batch to register
            await asyncio.sleep(batch_delay)

            # Count registrations from this batch
            for ev in batch_events:
                if ev.is_set():
                    registered_count += 1

            elapsed = time.time() - start_time
            logger.info(
                "Batch %d-%d launched (%d/%d registered so far, %.1fs elapsed)",
                batch_start,
                batch_end - 1,
                registered_count,
                batch_end,
                elapsed,
            )

        logger.info(
            "All %d clients launched in %.1fs. Running exchanges...",
            num_clients,
            time.time() - start_time,
        )

        # Run until cancelled
        await asyncio.gather(*tasks, return_exceptions=True)

    except asyncio.CancelledError:
        logger.info("Shutting down %d clients...", len(tasks))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await session.close()
        logger.info("All clients stopped.")
