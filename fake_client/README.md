# Fake Landscape Client

A lightweight load-testing tool that simulates thousands of Landscape Client
instances registering and exchanging messages with a Landscape Server.

## Features

- **Scalable**: Run 10,000+ fake clients simultaneously on a single machine
  using Python `asyncio` and connection pooling (no threads, no Twisted).
- **Realistic protocol**: Uses the real `bpickle` wire format and follows the
  actual Landscape Client registration and message exchange protocol.
- **Realistic data**: Each fake client reports believable system information:
  - Distribution info matching a real Ubuntu LTS series (focal, jammy, noble, or resolute)
  - Consistent package lists with ~150 packages per client, including
    realistic available upgrades and security updates
  - Randomized but plausible hardware profiles (memory, CPU, disk)
  - Periodic load averages, CPU usage, and memory stats with natural variation
- **Activity responses**: When the server sends activities (package changes,
  script execution, shutdown, resynchronize), clients respond with realistic
  random outcomes (90% success, 10% failure for package operations).
- **Staggered startup**: Clients register in configurable batches to avoid
  overwhelming the server with simultaneous registrations.
- **Graceful shutdown**: Handles SIGINT/SIGTERM for clean termination.

## Requirements

- Python 3.10+
- `aiohttp` (the only external dependency beyond the landscape-client repo)
- The `landscape` package (from this repository) must be importable for
  `bpickle` serialization

## Installation

From the repository root:

```bash
pip install aiohttp
# Ensure the landscape package is importable
pip install -e .  # or add the repo root to PYTHONPATH
```

## Usage

```bash
# Basic usage - 10,000 clients
python -m fake_client \
    --server-url https://landscape.example.com/message-system \
    --account-name my-account \
    --registration-key my-secret-key \
    --num-clients 10000

# Quick test with fewer clients and faster exchanges
python -m fake_client \
    --server-url https://landscape.example.com/message-system \
    --account-name my-account \
    --num-clients 100 \
    --exchange-interval 60

# With self-signed SSL certificate
python -m fake_client \
    --server-url https://landscape.local/message-system \
    --account-name standalone \
    --ssl-cert /path/to/ca.pem \
    --num-clients 5000

# Debug logging
python -m fake_client \
    --server-url https://landscape.example.com/message-system \
    --account-name my-account \
    --num-clients 10 \
    --log-level DEBUG
```

## CLI Options

| Option                  | Default | Description                                        |
|-------------------------|---------|----------------------------------------------------|
| `--server-url`          | —       | **Required.** Landscape server message-system URL. |
| `--account-name`        | —       | **Required.** Landscape account name.              |
| `--registration-key`    | None    | Registration key/password for the account.         |
| `--num-clients`         | 10000   | Number of fake clients to simulate.                |
| `--exchange-interval`   | 900     | Seconds between exchanges per client.              |
| `--batch-size`          | 100     | Clients to start per batch during ramp-up.         |
| `--batch-delay`         | 1.0     | Seconds between registration batches.              |
| `--ssl-cert`            | None    | Path to CA certificate for HTTPS verification.     |
| `--log-level`           | INFO    | Logging level (DEBUG, INFO, WARNING, ERROR).       |

## How It Works

### Registration
Each fake client sends a `register` message to the server containing:
- A unique computer title and hostname
- A deterministic machine ID
- VM info (`kvm`) and empty container info
- The configured account name and registration key

The server responds with `set-id` containing a `secure_id` and `insecure_id`,
which the client stores for all subsequent exchanges.

### Message Exchange
After registration, each client:
1. Sends an initial burst of system information (computer-info,
   distribution-info, processor-info, packages, etc.)
2. Enters a periodic exchange loop where it sends load averages, CPU usage,
   and occasional memory/disk info updates
3. Handles server-initiated activities (package changes, script execution,
   resynchronize) with realistic responses

### Package Reporting
Each client is assigned one of four Ubuntu LTS series. The package list for
each series contains ~150 real Ubuntu packages with correct version strings.
A configurable number of packages are marked as having available upgrades,
with a subset flagged as security updates.

### Performance
The tool uses:
- **asyncio** for cooperative concurrency (no threads)
- **aiohttp** with connection pooling (max 200 simultaneous connections)
- **Staggered exchanges** with 10% jitter to spread load
- **Batched registration** to control ramp-up

On a typical laptop, 10,000 clients consume ~200MB of RAM and produce
negligible CPU load between exchanges (they're mostly sleeping).

## Architecture

```
fake_client/
├── __init__.py       # Package marker
├── __main__.py       # CLI entry point (python -m fake_client)
├── client.py         # Core async client logic
├── packages.py       # Ubuntu LTS package data and helpers
└── README.md         # This file
```

The tool imports `bpickle` from the `landscape.lib` module in the parent
repository for wire-compatible serialization. All HTTP communication uses
`aiohttp` instead of `pycurl` for efficient async I/O.
