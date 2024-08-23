from typing import Dict, Type
from .tool import Tool

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self.register_all_tools()

    def register_tool(self, tool_cls: Type[Tool]):
        tool_instance = tool_cls()
        for schema in tool_instance.schema():
            self.tools[schema['function']['name']] = tool_instance

    def register_all_tools(self):
        for tool_cls in Tool.__subclasses__():
            self.register_tool(tool_cls)

    def get_tool(self, tool_name: str) -> Tool:
        return self.tools.get(tool_name)

    def get_all_tools(self) -> Dict[str, Tool]:
        return self.tools