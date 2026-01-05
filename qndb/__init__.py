"""
Core package for quantum database operations.

This package contains the fundamental components for quantum data processing,
including the quantum engine, encoding mechanisms, storage operations, and measurement protocols.
"""

from __future__ import annotations

import os
from typing import Optional

__version__ = '4.0.0'


def configure(
    *,
    ibm_api_key: Optional[str] = None,
    ionq_api_key: Optional[str] = None,
    google_project_id: Optional[str] = None,
    braket_device_arn: Optional[str] = None,
    env_file: str = "",
) -> None:
    """One-call setup for qndb API keys and hardware backends.

    Sets the corresponding environment variables so that hardware
    backends can pick them up at connection time.  Any key that is
    already set in the environment will **not** be overwritten unless
    explicitly passed here.

    Args:
        ibm_api_key: IBM Quantum API token.
        ionq_api_key: IonQ API key.
        google_project_id: Google Cloud project ID (authentication uses
            ``GOOGLE_APPLICATION_CREDENTIALS``).
        braket_device_arn: AWS Braket device ARN (authentication uses
            standard AWS credentials).
        env_file: Path to a ``.env`` file.  When empty, qndb will
            search ``./. env`` and ``../.env`` automatically.

    Example::

        import qndb

        # Option 1 — pass keys directly
        qndb.configure(ibm_api_key="your-key")

        # Option 2 — load from a .env file
        qndb.configure(env_file=".env")

        # Option 3 — just call configure() and it auto-loads .env
        qndb.configure()
    """
    from qndb.utilities.config import Configuration

    # Load .env first (won't override existing vars)
    Configuration.load_dotenv(env_file)

    _ENV_MAP = {
        "QNDB_IBM_API_KEY": ibm_api_key,
        "QNDB_IONQ_API_KEY": ionq_api_key,
        "QNDB_GOOGLE_PROJECT_ID": google_project_id,
        "QNDB_BRAKET_DEVICE_ARN": braket_device_arn,
    }

    # Also enable the corresponding backend flag automatically
    _FLAG_MAP = {
        "QNDB_IBM_API_KEY": "QNDB_IBM_ENABLED",
        "QNDB_IONQ_API_KEY": "QNDB_IONQ_ENABLED",
        "QNDB_GOOGLE_PROJECT_ID": "QNDB_GOOGLE_ENABLED",
        "QNDB_BRAKET_DEVICE_ARN": "QNDB_BRAKET_ENABLED",
    }

    any_hardware = False
    for env_var, value in _ENV_MAP.items():
        if value is not None:
            os.environ[env_var] = value
            # Auto-enable the flag too
            flag = _FLAG_MAP[env_var]
            os.environ.setdefault(flag, "1")
            any_hardware = True
        elif os.environ.get(env_var):
            # Key already in env (perhaps from .env file) — enable flag
            flag = _FLAG_MAP[env_var]
            os.environ.setdefault(flag, "1")
            any_hardware = True

    if any_hardware:
        os.environ.setdefault("QNDB_HARDWARE_ENABLED", "1")