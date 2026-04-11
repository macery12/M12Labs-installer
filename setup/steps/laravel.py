"""Step 4 – Configure the Laravel environment, run migrations, create admin user."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from setup.log import get_logger
from setup.system import run_as_www_data, run_command_no_cwd, with_privilege


def artisan(install_path: Path, *args: str) -> bool:
    """Run ``php artisan <args>`` in *install_path* as the ``www-data`` user.

    stdin/stdout/stderr are inherited so interactive artisan commands
    (e.g. ``p:environment:setup``, ``p:user:make``) pass straight through
    to the terminal.
    """
    return run_as_www_data(["php", "artisan", *args], cwd=install_path)


def _patch_env(env_path: Path, db_name: str, db_user: str, db_pass: str) -> None:
    """Overwrite DB_* entries in an existing ``.env`` file.

    Only lines whose keys match exactly are replaced; all other content is
    left unchanged.  The function never logs or prints the password value.
    """
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

    env_path.write_text(text, encoding="utf-8")


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
        run_command_no_cwd(chown_env_cmd)

    # Artisan commands
    artisan_steps = [
        (["key:generate", "--force"], "Generating application key…"),
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
        run_command_no_cwd(chown_cmd)

    logger.info("Step 4 complete: Laravel environment configured")
    print("  ✓ Laravel environment configured.")
    return True
