"""HomeKit control via the macOS `shortcuts` CLI."""

import asyncio
import logging
import shutil

log = logging.getLogger(__name__)

SHORTCUTS_BIN = shutil.which("shortcuts") or "/usr/bin/shortcuts"


class ShortcutError(RuntimeError):
    pass


async def run_shortcut(name: str, *, input_text: str | None = None, timeout: float = 15.0) -> str:
    args = [SHORTCUTS_BIN, "run", name]
    log.info("running shortcut: %s", name)
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.PIPE if input_text is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=input_text.encode() if input_text else None),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        raise ShortcutError(f"Shortcut '{name}' timed out after {timeout}s")
    if proc.returncode != 0:
        raise ShortcutError(
            f"Shortcut '{name}' exited {proc.returncode}: {stderr.decode().strip()}"
        )
    return stdout.decode().strip()


async def list_shortcuts() -> list[str]:
    proc = await asyncio.create_subprocess_exec(
        SHORTCUTS_BIN, "list",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    return [line.strip() for line in stdout.decode().splitlines() if line.strip()]
