"""PyrightClient: persistent pyright --lsp subprocess with LSP lifecycle.

Manages a single pyright language server process for hover-based type
inference. Lifecycle states: not_started → starting → ready → error
(→ restarting → ready). Bounded to MAX_RESTART_COUNT restarts before
entering permanent error state.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from src.mcp_codebase import config

logger = logging.getLogger(__name__)

# JSON-RPC Content-Length header
_HEADER_ENCODING = "ascii"
_CONTENT_ENCODING = "utf-8"


class PyrightClient:
    """Manages a persistent pyright --lsp subprocess for hover requests.

    Args:
        project_root: Absolute path to the project root (sent as rootUri).
    """

    def __init__(self, project_root: Path) -> None:
        """Initialize the instance."""
        self._project_root = project_root.resolve()
        self._state: str = "not_started"
        self._process: asyncio.subprocess.Process | None = None
        self._restart_count: int = 0
        self._request_id: int = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._reader_task: asyncio.Task[None] | None = None

    @property
    def state(self) -> str:
        """Execute the function."""
        return self._state

    # ------------------------------------------------------------------
    # JSON-RPC framing (T010a)
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _send(self, message: dict[str, Any]) -> None:
        """Send a JSON-RPC message with Content-Length framing."""
        assert self._process and self._process.stdin
        body = json.dumps(message).encode(_CONTENT_ENCODING)
        header = f"Content-Length: {len(body)}\r\n\r\n".encode(_HEADER_ENCODING)
        self._process.stdin.write(header + body)
        await self._process.stdin.drain()

    async def _send_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send a JSON-RPC request and await the response by id correlation."""
        req_id = self._next_id()
        msg: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            msg["params"] = params

        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[req_id] = future

        await self._send(msg)

        try:
            return await asyncio.wait_for(
                future, timeout=config.LSP_REQUEST_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise

    async def _send_notification(
        self, method: str, params: dict[str, Any] | None = None
    ) -> None:
        """Send a JSON-RPC notification (no id, no response expected)."""
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        await self._send(msg)

    async def _read_message(
        self, reader: asyncio.StreamReader
    ) -> dict[str, Any] | None:
        """Read one JSON-RPC message from the stream (Content-Length framing)."""
        content_length: int | None = None

        while True:
            line = await reader.readline()
            if not line:
                return None  # EOF
            decoded = line.decode(_HEADER_ENCODING).strip()
            if not decoded:
                break  # End of headers
            if decoded.lower().startswith("content-length:"):
                content_length = int(decoded.split(":", 1)[1].strip())

        if content_length is None:
            return None

        body = await reader.readexactly(content_length)
        return json.loads(body.decode(_CONTENT_ENCODING))

    async def _reader_loop(self) -> None:
        """Background task: read JSON-RPC responses and dispatch to pending futures."""
        assert self._process and self._process.stdout
        try:
            while True:
                msg = await self._read_message(self._process.stdout)
                if msg is None:
                    break  # Process exited

                msg_id = msg.get("id")
                if msg_id is not None and msg_id in self._pending:
                    future = self._pending.pop(msg_id)
                    if not future.done():
                        future.set_result(msg)
                # Notifications (no id) are ignored — we don't use push diagnostics
        except (asyncio.CancelledError, asyncio.IncompleteReadError):
            pass
        except Exception:
            logger.exception("pyright_client: reader loop error")
        finally:
            # Resolve any pending futures with an error so callers don't hang
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(
                        ConnectionError("pyright process exited unexpectedly")
                    )
            self._pending.clear()

    # ------------------------------------------------------------------
    # Lifecycle (T010b, T010c, T010d)
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Launch pyright --lsp and perform LSP initialization handshake."""
        self._state = "starting"
        try:
            self._process = await asyncio.create_subprocess_exec(
                config.PYRIGHT_LSP_COMMAND,
                *config.PYRIGHT_LSP_ARGS,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Start the reader loop
            self._reader_task = asyncio.create_task(self._reader_loop())

            # LSP initialize
            root_uri = self._project_root.as_uri()
            init_params = {
                "processId": None,
                "rootUri": root_uri,
                "capabilities": {},
                "workspaceFolders": [{"uri": root_uri, "name": self._project_root.name}],
            }

            response = await asyncio.wait_for(
                self._send_request("initialize", init_params),
                timeout=config.LSP_INITIALIZE_TIMEOUT_S,
            )

            if "error" in response:
                raise RuntimeError(
                    f"LSP initialize failed: {response['error']}"
                )

            # Send initialized notification
            await self._send_notification("initialized", {})

            self._state = "ready"
            logger.info(
                "pyright_client: ready",
                extra={"project_root": str(self._project_root)},
            )

        except Exception:
            self._state = "error"
            logger.exception("pyright_client: startup failed")
            await self._kill_process()
            raise

    async def _restart(self) -> None:
        """Attempt to restart the pyright subprocess (bounded by MAX_RESTART_COUNT)."""
        self._restart_count += 1
        if self._restart_count > config.MAX_RESTART_COUNT:
            self._state = "error"
            logger.error(
                "pyright_client: max restarts exceeded, entering permanent error state",
                extra={"restart_count": self._restart_count},
            )
            return

        self._state = "restarting"
        logger.warning(
            "pyright_client: restarting",
            extra={"restart_attempt": self._restart_count},
        )

        await self._kill_process()

        try:
            await self.start()
        except Exception:
            if self._restart_count >= config.MAX_RESTART_COUNT:
                self._state = "error"

    async def shutdown(self) -> None:
        """Graceful shutdown: shutdown request → exit notification → wait → kill."""
        if self._state == "not_started":
            return

        self._state = "shutdown"

        if self._process and self._process.returncode is None:
            try:
                # Send LSP shutdown request
                await asyncio.wait_for(
                    self._send_request("shutdown"),
                    timeout=config.LSP_SHUTDOWN_TIMEOUT_S,
                )
                # Send exit notification
                await self._send_notification("exit")
                # Wait for process to terminate
                await asyncio.wait_for(
                    self._process.wait(),
                    timeout=config.LSP_SHUTDOWN_TIMEOUT_S,
                )
            except (asyncio.TimeoutError, ConnectionError, Exception):
                logger.warning("pyright_client: graceful shutdown failed, killing")
                await self._kill_process()
        else:
            await self._kill_process()

    async def _kill_process(self) -> None:
        """Force-kill the subprocess and cancel the reader task."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._process and self._process.returncode is None:
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass

    # ------------------------------------------------------------------
    # Hover (used by get_type tool — T016 will extend)
    # ------------------------------------------------------------------

    async def hover(
        self, file_path: Path, *, line: int, column: int
    ) -> str | None:
        """Send textDocument/hover and return the parsed type string.

        Returns None if the client is not ready or hover returns no result.
        Line is 1-based (converted to 0-based for LSP). Column is 0-based.
        """
        if self._state not in ("ready",):
            return None

        # Check if process is still alive
        if self._process and self._process.returncode is not None:
            await self._restart()
            if self._state != "ready":
                return None

        uri = file_path.resolve().as_uri()
        text = file_path.read_text(encoding="utf-8")

        # didOpen
        await self._send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": "python",
                    "version": 1,
                    "text": text,
                }
            },
        )

        try:
            # hover request (line is 0-based in LSP)
            response = await self._send_request(
                "textDocument/hover",
                {
                    "textDocument": {"uri": uri},
                    "position": {"line": line - 1, "character": column},
                },
            )
        except (asyncio.TimeoutError, ConnectionError):
            return None
        finally:
            # didClose
            try:
                await self._send_notification(
                    "textDocument/didClose",
                    {"textDocument": {"uri": uri}},
                )
            except Exception:
                pass

        result = response.get("result")
        if not result:
            return None

        contents = result.get("contents", {})
        value = contents.get("value", "") if isinstance(contents, dict) else str(contents)

        return self._parse_hover_markdown(value) if value else None

    @staticmethod
    def _parse_hover_markdown(markdown: str) -> str | None:
        """Extract type information from pyright hover markdown.

        Handles known pyright hover prefixes:
        - (variable) name: type
        - (function) def name(...) -> type
        - (method) def name(self, ...) -> type
        - (parameter) name: type
        - (property) name: type
        - (class) class Name
        - (type alias) Name = type
        - (module) name
        """
        # Strip markdown code fences if present
        lines = markdown.strip().split("\n")
        content_lines: list[str] = []
        in_code_block = False
        for raw_line in lines:
            stripped = raw_line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block or not stripped.startswith("---"):
                content_lines.append(stripped)

        if not content_lines:
            return None

        first_line = content_lines[0]

        # Handle known prefix formats
        prefixes = [
            "(variable)", "(function)", "(method)", "(parameter)",
            "(property)", "(class)", "(type alias)", "(module)",
        ]
        for prefix in prefixes:
            if first_line.startswith(prefix):
                rest = first_line[len(prefix):].strip()
                return rest if rest else None

        return None
