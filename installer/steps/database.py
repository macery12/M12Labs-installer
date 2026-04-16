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

import os
import re
import shutil
import subprocess

from installer.log import get_logger

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


def check_credentials(
    db_host: str,
    db_user: str,
    db_pass: str,
    db_port: str = "3306",
) -> bool:
    """Verify MySQL/MariaDB credentials without requiring the target database to exist.

    Connects to the server without selecting any database so that
    authentication can be validated independently of database existence.
    This function is read-only and never creates any database objects.

    The password is passed via the ``MYSQL_PWD`` environment variable so it
    never appears in the process argument list.

    Args:
        db_host: MySQL/MariaDB host (e.g. ``127.0.0.1``).
        db_user: Database user.
        db_pass: Database password (never logged or persisted).
        db_port: TCP port (default: ``"3306"``).

    Returns:
        ``True`` when authentication succeeds, ``False`` otherwise.
    """
    logger = get_logger()

    if not shutil.which("mysql"):
        logger.warning("check_credentials: mysql client not found")
        return False

    env = os.environ.copy()
    env["MYSQL_PWD"] = db_pass

    try:
        result = subprocess.run(
            [
                "mysql",
                "-h", db_host,
                "-P", str(db_port),
                "-u", db_user,
                "--connect-timeout", "10",
                "-e", "SELECT 1;",
            ],
            env=env,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("check_credentials: connection timed out")
        return False
    except FileNotFoundError:
        logger.warning("check_credentials: mysql binary not found")
        return False

    success = result.returncode == 0
    if not success:
        stderr = result.stderr.decode(errors="replace").strip()
        logger.debug(
            "check_credentials failed (exit %d): %s", result.returncode, stderr
        )
    return success


def database_exists(
    db_host: str,
    db_name: str,
    db_user: str,
    db_pass: str,
    db_port: str = "3306",
) -> bool:
    """Check whether a named database exists without connecting to it directly.

    Queries ``information_schema.SCHEMATA`` so the check is entirely
    read-only and never creates any database objects.  Call
    :func:`check_credentials` first to confirm the credentials are valid
    before calling this function.

    The password is passed via the ``MYSQL_PWD`` environment variable so it
    never appears in the process argument list.

    Args:
        db_host: MySQL/MariaDB host (e.g. ``127.0.0.1``).
        db_name: Database name to look up.
        db_user: Database user.
        db_pass: Database password (never logged or persisted).
        db_port: TCP port (default: ``"3306"``).

    Returns:
        ``True`` when the database exists and is visible to the user,
        ``False`` when it does not exist or on error.
    """
    logger = get_logger()

    if not shutil.which("mysql"):
        logger.warning("database_exists: mysql client not found")
        return False

    # Escape the database name for use in a SQL string literal.
    # db_name is also validated by callers via _validate_identifier, so
    # single quotes and backslashes should never be present in practice.
    escaped_name = db_name.replace("\\", "\\\\").replace("'", "\\'")
    sql = (
        f"SELECT SCHEMA_NAME FROM information_schema.SCHEMATA"
        f" WHERE SCHEMA_NAME = '{escaped_name}' LIMIT 1;"
    )

    env = os.environ.copy()
    env["MYSQL_PWD"] = db_pass

    try:
        result = subprocess.run(
            [
                "mysql",
                "-h", db_host,
                "-P", str(db_port),
                "-u", db_user,
                "--connect-timeout", "10",
                "-e", sql,
            ],
            env=env,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("database_exists: connection timed out")
        return False
    except FileNotFoundError:
        logger.warning("database_exists: mysql binary not found")
        return False

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        logger.debug(
            "database_exists query failed (exit %d): %s", result.returncode, stderr
        )
        return False

    stdout = result.stdout.decode(errors="replace")
    return db_name in stdout


def check_db_connection(
    db_host: str,
    db_name: str,
    db_user: str,
    db_pass: str,
    db_port: str = "3306",
) -> bool:
    """Test whether a database connection can be established with the given credentials.

    This function is read-only and never creates any database objects.
    If you need to distinguish between an authentication failure and a
    missing database, use :func:`check_credentials` followed by
    :func:`database_exists` instead.

    The password is passed via the ``MYSQL_PWD`` environment variable so it
    never appears in the process argument list.

    Args:
        db_host: MySQL/MariaDB host (e.g. ``127.0.0.1``).
        db_name: Database name to connect to.
        db_user: Database user.
        db_pass: Database password (never logged or persisted).
        db_port: TCP port (default: ``"3306"``).

    Returns:
        ``True`` when the connection succeeds, ``False`` otherwise.
    """
    logger = get_logger()

    if not shutil.which("mysql"):
        logger.warning("check_db_connection: mysql client not found")
        return False

    env = os.environ.copy()
    env["MYSQL_PWD"] = db_pass

    try:
        result = subprocess.run(
            [
                "mysql",
                "-h", db_host,
                "-P", str(db_port),
                "-u", db_user,
                db_name,
                "-e", "SELECT 1;",
            ],
            env=env,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("check_db_connection: connection timed out")
        return False
    except FileNotFoundError:
        logger.warning("check_db_connection: mysql binary not found")
        return False

    success = result.returncode == 0
    if not success:
        stderr = result.stderr.decode(errors="replace").strip()
        logger.debug(
            "check_db_connection failed (exit %d): %s", result.returncode, stderr
        )
    return success
