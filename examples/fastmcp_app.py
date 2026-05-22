from fastmcp import FastMCP

from microbootstrap import FastMcpSettings
from microbootstrap.bootstrappers.fastmcp import FastMcpBootstrapper


class Settings(FastMcpSettings):
    service_name: str = "example-mcp"
    service_description: str = "Example FastMCP service"


application: FastMCP = FastMcpBootstrapper(Settings()).bootstrap()


@application.tool
def greet_person(person_name: str) -> str:
    return f"Hello, {person_name}!"
