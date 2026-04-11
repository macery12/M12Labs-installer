"""Step 3 – Create the MySQL/MariaDB database and user.

Translates the ``database-setup.md`` documentation page:

    CREATE USER IF NOT EXISTS '<user>'@'127.0.0.1' IDENTIFIED BY '<pass>';
    CREATE DATABASE IF NOT EXISTS `<db_name>`;
    GRANT ALL PRIVILEGES ON `<db_name>`.* TO '<user>'@'127.0.0.1'
        WITH GRANT OPTION;
    FLUSH PRIVILEGES;

The SQL is passed to ``mysql`` via **stdin** (not via ``-e``) to avoid
exposing the password in the process argument list.

Security:
    - db_name is validated to contain only alphanumeric characters and
      underscores (safe for use as a backtick-quoted MySQL identifier).
    - db_user is validated the same way.
    - db_pass is passed only through stdin; it is never logged.
"""

from __future__ import annotations

import re
import shutil
import subprocess

from setup.log import get_logger

_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")

# Maximum length limits that match MySQL's own constraints.
_MAX_IDENTIFIER_LEN = 64
_MAX_USER_LEN = 32


def _validate_identifier(value: str, label: str) -> str | None:
    """Return an error message if *value* is not a safe MySQL identifier, else None."""
    if not value:
        return f"{label} must not be empty"
    if len(value) > _MAX_IDENTIFIER_LEN:
        return f"{label} is too long (max {_MAX_IDENTIFIER_LEN} characters)"
    if not _SAFE_IDENTIFIER_RE.match(value):
        return f"{label} must contain only letters, digits, and underscores"
    return None


def _validate_user(value: str) -> str | None:
    if not value:
        return "DB user must not be empty"
    if len(value) > _MAX_USER_LEN:
        return f"DB user is too long (max {_MAX_USER_LEN} characters)"
    if not _SAFE_IDENTIFIER_RE.match(value):
        return "DB user must contain only letters, digits, and underscores"
    return None


def setup_database(db_name: str, db_user: str, db_pass: str) -> bool:
    """Create the database and MySQL user for the M12Labs panel.

    Args:
        db_name: Name for the new database.
        db_user: MySQL user to create.
        db_pass: Password for the new user (never logged or persisted).

    Returns:
        ``True`` on success, ``False`` on failure.
    """
    logger = get_logger()
    logger.info(
        "Step 3: Setting up database: db_name=%s, db_user=%s", db_name, db_user
    )
    print("\n[3/5] Setting up database…")

    # Input validation
    name_error = _validate_identifier(db_name, "DB name")
    if name_error:
        print(f"  ERROR: {name_error}")
        logger.error("Database setup validation failed: %s", name_error)
        return False

    user_error = _validate_user(db_user)
    if user_error:
        print(f"  ERROR: {user_error}")
        logger.error("Database setup validation failed: %s", user_error)
        return False

    if not db_pass:
        print("  ERROR: DB password must not be empty.")
        logger.error("DB password is empty")
        return False

    if not shutil.which("mysql"):
        print("  ERROR: mysql client not found. Is MariaDB/MySQL installed?")
        logger.error("mysql client not found")
        return False

    # Escape single quotes in the password for safe use in SQL strings
    escaped_pass = db_pass.replace("\\", "\\\\").replace("'", "\\'")

    sql = (
        f"CREATE DATABASE IF NOT EXISTS `{db_name}`;\n"
        f"CREATE USER IF NOT EXISTS '{db_user}'@'127.0.0.1'"
        f" IDENTIFIED BY '{escaped_pass}';\n"
        f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'127.0.0.1'"
        " WITH GRANT OPTION;\n"
        "FLUSH PRIVILEGES;\n"
    )

    print(f"  Creating database '{db_name}' and user '{db_user}'…")
    # Pass SQL via stdin so the password never appears in the argument list
    try:
        result = subprocess.run(
            ["mysql", "-u", "root"],
            input=sql.encode(),
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        print("  ERROR: mysql command not found.")
        logger.error("mysql binary not found")
        return False

    if result.returncode != 0:
        print("  ERROR: MySQL command failed. Check that MariaDB is running")
        print("         and that the root user can connect without a password,")
        print("         or re-run with `sudo`.")
        # Print stderr to help diagnose (never contains the password)
        if result.stderr:
            print(result.stderr.decode(errors="replace").strip())
        logger.error("mysql command exited with code %d", result.returncode)
        return False

    logger.info("Step 3 complete: database and user created")
    print("  ✓ Database and user created.")
    return True
