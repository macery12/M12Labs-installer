"""Step 4 – Configure the Laravel environment, run migrations, create admin user."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from installer.log import get_logger
from installer.system import read_env_value, run_as_www_data, run_command, with_privilege


def artisan(install_path: Path, *args: str) -> bool:
    """Run ``php artisan <args>`` in *install_path* as the ``www-data`` user.

    stdin/stdout/stderr are inherited so interactive artisan commands
    (e.g. ``p:environment:setup``, ``p:user:make``) pass straight through
    to the terminal.
    """
    return run_as_www_data(["php", "artisan", *args], cwd=install_path)


def _read_env_value(env_path: Path, key: str) -> str | None:
    """Thin wrapper around :func:`~installer.system.read_env_value` for this module."""
    return read_env_value(env_path, key)


def _patch_env(env_path: Path, db_name: str, db_user: str, db_pass: str) -> None:
    """Overwrite DB_* entries in an existing ``.env`` file using an atomic write.

    Only lines whose keys match exactly are replaced; all other content is
    left unchanged.  The function never logs or prints the password value.
    Uses a tempfile-then-replace pattern so a crash mid-write cannot corrupt
    the ``.env``.
    """
    import os as _os
    import tempfile as _tempfile

    text = env_path.read_text(encoding="utf-8")

    replacements = {
        "DB_DATABASE": db_name,
        "DB_USERNAME": db_user,
        "DB_PASSWORD": db_pass,
    }

    for key, value in replacements.items():
        pattern = re.compile(rf"^({re.escape(key)}=).*$", re.MULTILINE)
        replacement = rf"\g<1>{value}"
        if pattern.search(text):
            text = pattern.sub(replacement, text)
        else:
            # Key absent – append it
            text = text.rstrip("\n") + f"\n{key}={value}\n"

    # Write atomically: temp file in the same directory → fsync → os.replace
    parent = env_path.parent
    fd, tmp_path = _tempfile.mkstemp(dir=parent, prefix=".env_tmp_")
    try:
        with _os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            _os.fsync(fh.fileno())
        _os.replace(tmp_path, env_path)
    except Exception:
        try:
            _os.unlink(tmp_path)
        except OSError:
            pass
        raise


def configure_laravel(
    install_path: Path,
    db_name: str,
    db_user: str,
    db_pass: str,
) -> bool:
    """Configure the Laravel environment and run all required artisan commands.

    Args:
        install_path: Root of the installed panel (e.g. ``/var/www/m12labs``).
        db_name:      Database name (persisted into ``.env``).
        db_user:      Database user (persisted into ``.env``).
        db_pass:      Database password – written to ``.env`` only, never
                      logged or persisted anywhere else.

    Returns:
        ``True`` on success, ``False`` on first failure.
    """
    logger = get_logger()
    logger.info("Step 4: Configuring Laravel environment at %s", install_path)
    print("\n[4/5] Configuring Laravel environment…")

    if not shutil.which("php"):
        print("  ERROR: php not found. Did Step 1 complete successfully?")
        logger.error("php not found")
        return False

    if not shutil.which("composer"):
        print("  ERROR: composer not found. Did Step 1 complete successfully?")
        logger.error("composer not found")
        return False

    env_path = install_path / ".env"
    env_example = install_path / ".env.example"

    # Copy .env.example to .env
    if not env_path.exists():
        if env_example.exists():
            print("  Copying .env.example → .env…")
            try:
                shutil.copy2(str(env_example), str(env_path))
            except OSError as exc:
                print(f"  ERROR: could not copy .env.example: {exc}")
                logger.error("Failed to copy .env.example: %s", exc)
                return False
        else:
            print("  WARNING: .env.example not found – creating a minimal .env.")
            logger.warning(".env.example not found at %s", env_example)
            env_path.write_text("APP_ENV=production\n", encoding="utf-8")

    # Patch .env with DB credentials
    print("  Writing database credentials to .env…")
    logger.debug("Patching .env with DB_DATABASE=%s, DB_USERNAME=%s", db_name, db_user)
    try:
        _patch_env(env_path, db_name, db_user, db_pass)
    except OSError as exc:
        print(f"  ERROR: could not write .env: {exc}")
        logger.error("Failed to patch .env: %s", exc)
        return False

    # Composer install
    print("  Running composer install (this may take a few minutes)…")
    if not run_as_www_data(
        ["composer", "install", "--no-dev", "--optimize-autoloader"],
        cwd=install_path,
    ):
        print("  ERROR: composer install failed.")
        logger.error("composer install failed")
        return False

    # Ensure www-data owns .env so artisan key:generate can write to it
    chown_env_cmd = with_privilege(["chown", "www-data:www-data", str(env_path)])
    if chown_env_cmd:
        run_command(chown_env_cmd)

    # Artisan commands
    # Only generate a new APP_KEY when one is not already present.
    existing_app_key = _read_env_value(env_path, "APP_KEY")
    if existing_app_key:
        print("  APP_KEY already present in .env – skipping key generation.")
        logger.info("APP_KEY already set; skipping key:generate")

    artisan_steps = [
        *(
            []
            if existing_app_key
            else [(["key:generate", "--force"], "Generating application key…")]
        ),
        (["p:environment:setup"], "Running environment setup (answer prompts below)…"),
        (["migrate", "--seed", "--force"], "Running database migrations…"),
        (["p:user:make"], "Creating admin user (answer prompts below)…"),
    ]

    for args, description in artisan_steps:
        print(f"  {description}")
        if not artisan(install_path, *args):
            print(f"  ERROR: php artisan {' '.join(args)} failed.")
            logger.error("artisan %s failed", " ".join(args))
            return False

    # Reset ownership to www-data
    print("  Resetting file ownership to www-data:www-data…")
    chown_cmd = with_privilege(
        ["chown", "-R", "www-data:www-data", str(install_path)]
    )
    if chown_cmd:
        run_command(chown_cmd)

    logger.info("Step 4 complete: Laravel environment configured")
    print("  ✓ Laravel environment configured.")
    return True


def update_laravel(install_path: Path) -> bool:
    """Run the minimal steps needed to refresh an existing panel installation.

    Performs, in order:

    1. ``composer install --no-dev --optimize-autoloader``
    2. ``php artisan optimize:clear``
    3. ``php artisan migrate --seed --force``
    4. ``chown -R www-data:www-data <install_path>``
    5. ``php artisan up``

    The function does **not** patch ``.env``, generate keys, or create
    admin users – those tasks are for the full install flow only.

    Args:
        install_path: Root of the installed panel.

    Returns:
        ``True`` on success, ``False`` on first failure.
    """
    logger = get_logger()
    logger.info("Update: Running Laravel refresh steps at %s", install_path)
    print("\nRunning Laravel refresh steps…")

    if not shutil.which("php"):
        print("  ERROR: php not found.")
        logger.error("php not found")
        return False

    if not shutil.which("composer"):
        print("  ERROR: composer not found.")
        logger.error("composer not found")
        return False

    # Composer install
    print("  Running composer install (this may take a few minutes)…")
    if not run_as_www_data(
        ["composer", "install", "--no-dev", "--optimize-autoloader"],
        cwd=install_path,
    ):
        print("  ERROR: composer install failed.")
        logger.error("composer install failed")
        return False

    # Clear optimized caches
    print("  Clearing optimized caches…")
    if not artisan(install_path, "optimize:clear"):
        print("  ERROR: php artisan optimize:clear failed.")
        logger.error("artisan optimize:clear failed")
        return False

    # Database migrations
    print("  Running database migrations…")
    if not artisan(install_path, "migrate", "--seed", "--force"):
        print("  ERROR: php artisan migrate --seed --force failed.")
        logger.error("artisan migrate --seed --force failed")
        return False

    # Reset ownership
    print("  Resetting file ownership to www-data:www-data…")
    chown_cmd = with_privilege(
        ["chown", "-R", "www-data:www-data", str(install_path)]
    )
    if chown_cmd:
        run_command(chown_cmd)

    # Bring application back online
    print("  Bringing application back online…")
    if not artisan(install_path, "up"):
        print("  WARNING: php artisan up failed – application may still be in maintenance mode.")
        logger.warning("artisan up failed; application may be in maintenance mode")
    else:
        logger.info("Application brought back online")

    logger.info("Update: Laravel refresh complete at %s", install_path)
    print("  ✓ Laravel refresh complete.")
    return True
