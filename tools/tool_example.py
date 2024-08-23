from typing import List, Dict, Any
from .tool import Tool, ToolResult

class ExampleTool(Tool):
    def __init__(self):
        super().__init__()

    async def example_function(self, input_text: str) -> ToolResult:
        try:
            processed_text = input_text.upper()
            return self.success_response({
                "original_text": input_text,
                "processed_text": processed_text
            })
        except Exception as e:
            return self.fail_response(f"Error processing input: {str(e)}")

    def schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "example_function",
                    "description": "An example function that demonstrates the usage of the Tool class",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "input_text": {
                                "type": "string",
                                "description": "The text to be processed by the example function"
                            }
                        },
                        "required": ["input_text"]
                    }
                }
            }
        ]