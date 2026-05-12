#!/usr/bin/env python3
"""CLI entry point for the Fake Landscape Client.

Usage:
    python -m fake_client \
        --server-url https://landscape.example.com/message-system \
        --account-name my-account \
        --num-clients 10000

See --help for all options.
"""

import argparse
import asyncio
import logging
import signal
import sys

from .client import run_many_clients


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fake-landscape-client",
        description=(
            "Fake Landscape Client for load testing. "
            "Simulates many landscape-client instances enrolling and "
            "exchanging messages with a Landscape Server."
        ),
    )

    parser.add_argument(
        "--server-url",
        required=True,
        help=(
            "The Landscape server message-system URL. "
            "Example: https://landscape.example.com/message-system"
        ),
    )
    parser.add_argument(
        "--account-name",
        required=True,
        help="The Landscape account name to register under.",
    )
    parser.add_argument(
        "--registration-key",
        default=None,
        help="Optional registration key/password for the account.",
    )
    parser.add_argument(
        "--num-clients",
        type=int,
        default=10000,
        help="Number of fake clients to simulate (default: 10000).",
    )
    parser.add_argument(
        "--exchange-interval",
        type=float,
        default=900.0,
        help=(
            "Seconds between message exchanges per client (default: 900). "
            "Lower values increase server load."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help=(
            "Number of clients to start per batch (default: 100). "
            "Controls registration ramp-up speed."
        ),
    )
    parser.add_argument(
        "--batch-delay",
        type=float,
        default=1.0,
        help="Seconds to wait between batches (default: 1.0).",
    )
    parser.add_argument(
        "--ssl-cert",
        default=None,
        help="Path to SSL CA certificate for HTTPS verification.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO).",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    main_task = loop.create_task(
        run_many_clients(
            num_clients=args.num_clients,
            server_url=args.server_url,
            account_name=args.account_name,
            registration_key=args.registration_key,
            exchange_interval=args.exchange_interval,
            ssl_cert=args.ssl_cert,
            batch_size=args.batch_size,
            batch_delay=args.batch_delay,
        ),
    )

    # Handle graceful shutdown on SIGINT/SIGTERM
    def shutdown(sig):
        logging.getLogger("fake_client").info(
            "Received signal %s, shutting down...",
            sig.name,
        )
        main_task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown, sig)

    try:
        loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        pass
    finally:
        loop.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
