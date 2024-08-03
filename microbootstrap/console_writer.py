from __future__ import annotations
import dataclasses
import typing

from rich.console import Console
from rich.rule import Rule
from rich.table import Table


@dataclasses.dataclass
class ConsoleWriter:
    writer_enabled: bool = True
    rich_console: Console = dataclasses.field(init=False, default_factory=Console)
    rich_table: Table = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        self.rich_table = Table(show_header=False, header_style="cyan")
        self.rich_table.add_column("Item", style="cyan")
        self.rich_table.add_column("Status")
        self.rich_table.add_column("Reason", style="yellow")

    def write_instrument_status(
        self,
        instrument_name: str,
        is_enabled: bool,
        disable_reason: str | None = None,
    ) -> None:
        is_enabled_value: typing.Final = "[green]Enabled[/green]" if is_enabled else "[red]Disabled[/red]"
        self.rich_table.add_row(rf"{instrument_name}", is_enabled_value, disable_reason or "")

    def print_bootstrap_table(self) -> None:
        if self.writer_enabled:
            self.rich_console.print(Rule("[yellow]Bootstrapping application[/yellow]", align="left"))
            self.rich_console.print(self.rich_table)
