"""DEPRECATED – install path management has been consolidated into ``config.py``.

This module is no longer used by the launcher.  All install-path logic
(loading, saving, and prompting) is handled exclusively by
:mod:`config` (:func:`config.ensure_install_path`,
:func:`config.prompt_for_install_path`, :func:`config.save_config`).

This file is kept to avoid import errors in any external scripts that may
reference it, but every public function now raises :class:`RuntimeError` to
make accidental usage obvious during development.
"""

from __future__ import annotations


def load_saved_install_path():  # type: ignore[return]
    raise RuntimeError(
        "install_path.load_saved_install_path is deprecated. "
        "Use config.load_config() instead."
    )


def save_install_path(path):  # type: ignore[return]
    raise RuntimeError(
        "install_path.save_install_path is deprecated. "
        "Use config.save_config() instead."
    )


def prompt_for_install_path():  # type: ignore[return]
    raise RuntimeError(
        "install_path.prompt_for_install_path is deprecated. "
        "Use config.prompt_for_install_path() instead."
    )


def get_install_path():  # type: ignore[return]
    raise RuntimeError(
        "install_path.get_install_path is deprecated. "
        "Use config.ensure_install_path() instead."
    )
