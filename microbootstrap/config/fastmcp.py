from __future__ import annotations
import dataclasses
import typing


if typing.TYPE_CHECKING:
    import mcp.types
    from fastmcp.client.sampling import SamplingHandler
    from fastmcp.server.auth import AuthProvider
    from fastmcp.server.lifespan import Lifespan
    from fastmcp.server.middleware import Middleware as FastMcpMiddleware
    from fastmcp.server.providers import Provider
    from fastmcp.server.server import DuplicateBehavior, LifespanCallable
    from fastmcp.server.transforms import Transform
    from fastmcp.tools.base import Tool
    from key_value.aio.protocols import AsyncKeyValue


@dataclasses.dataclass
class FastMcpConfig:
    name: str | None = None
    instructions: str | None = None
    version: str | int | float | None = None
    website_url: str | None = None
    icons: list[mcp.types.Icon] | None = None
    auth: AuthProvider | None = None
    middleware: typing.Sequence[FastMcpMiddleware] | None = None
    providers: typing.Sequence[Provider] | None = None
    transforms: typing.Sequence[Transform] | None = None
    lifespan: LifespanCallable | Lifespan | None = None
    tools: typing.Sequence[Tool | typing.Callable[..., typing.Any]] | None = None
    on_duplicate: DuplicateBehavior | None = None
    mask_error_details: bool | None = None
    dereference_schemas: bool = True
    strict_input_validation: bool | None = None
    list_page_size: int | None = None
    tasks: bool | None = None
    session_state_store: AsyncKeyValue | None = None
    sampling_handler: SamplingHandler[typing.Any, typing.Any] | None = None
    sampling_handler_behavior: typing.Literal["always", "fallback"] | None = None
    client_log_level: mcp.types.LoggingLevel | None = None
    experimental_capabilities: dict[str, dict[str, typing.Any]] | None = None
