import json
import logging
import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from db import Database, Thread, ThreadRun
from tools.tool import Tool, ToolResult
from llm import make_llm_api_call
from tools import ExampleTool 
from working_memory_manager import WorkingMemory
from datetime import datetime
from tools.tool_registry import ToolRegistry

class MessageThreadManager:
    def __init__(self, db: Database):
        self.db = db
        self.working_memory = WorkingMemory(db)
        self.tool_registry = ToolRegistry()

    async def create_thread(self) -> int:
        async with self.db.get_async_session() as session:
            creation_date = datetime.now().isoformat()
            new_thread = Thread(
                messages=json.dumps([]),
                creation_date=creation_date,
                last_updated_date=creation_date
            )
            session.add(new_thread)
            await session.commit()
            return new_thread.thread_id

    async def add_message(self, thread_id: int, message_data: Dict[str, Any], images: Optional[List[Dict[str, Any]]] = None):
        async with self.db.get_async_session() as session:
            thread = await session.get(Thread, thread_id)
            if not thread:
                raise ValueError(f"Thread with id {thread_id} not found")

            try:
                messages = json.loads(thread.messages)
                
                # If we're adding a user message, perform checks
                if message_data['role'] == 'user':
                    # Find the last assistant message with tool calls
                    last_assistant_index = next((i for i in reversed(range(len(messages))) if messages[i]['role'] == 'assistant' and 'tool_calls' in messages[i]), None)
                    
                    if last_assistant_index is not None:
                        tool_call_count = len(messages[last_assistant_index]['tool_calls'])
                        tool_response_count = sum(1 for msg in messages[last_assistant_index+1:] if msg['role'] == 'tool')
                        
                        if tool_call_count != tool_response_count:
                            raise ValueError(f"Incomplete tool responses. Expected {tool_call_count}, but got {tool_response_count}")

                # Convert ToolResult objects to strings
                for key, value in message_data.items():
                    if isinstance(value, ToolResult):
                        message_data[key] = str(value)

#                 # Process images if present
#                 if images:
#                     content = message_data.get('content', '')
#                     for image in images:
#                         filename = image.get('filename', 'unknown_file')
#                         image_type = image.get('content_type', 'image/unknown')
#                         image_analysis = image.get('analysis', 'No analysis available')
                        
#                         image_content = f"""<uploadedImage filename="{filename}" type="{image_type}">
# {image_analysis}
# </uploadedImage>"""
#                         content += f"\n\n{image_content}"
                    
#                     message_data['content'] = content

                messages.append(message_data)
                thread.messages = json.dumps(messages)
                thread.last_updated_date = datetime.now().isoformat()
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e

    async def get_message(self, thread_id: int, message_index: int) -> Optional[Dict[str, Any]]:
        async with self.db.get_async_session() as session:
            thread = await session.get(Thread, thread_id)
            if not thread:
                return None
            messages = json.loads(thread.messages)
            if message_index < len(messages):
                return messages[message_index]
            return None

    async def modify_message(self, thread_id: int, message_index: int, new_message_data: Dict[str, Any]):
        async with self.db.get_async_session() as session:
            thread = await session.get(Thread, thread_id)
            if not thread:
                raise ValueError(f"Thread with id {thread_id} not found")

            try:
                messages = json.loads(thread.messages)
                if message_index < len(messages):
                    messages[message_index] = new_message_data
                    thread.messages = json.dumps(messages)
                    thread.last_updated_date = datetime.now().isoformat()
                    await session.commit()
            except Exception as e:
                await session.rollback()
                raise e

    async def remove_message(self, thread_id: int, message_index: int):
        async with self.db.get_async_session() as session:
            thread = await session.get(Thread, thread_id)
            if not thread:
                raise ValueError(f"Thread with id {thread_id} not found")

            try:
                messages = json.loads(thread.messages)
                if message_index < len(messages):
                    del messages[message_index]
                    thread.messages = json.dumps(messages)
                    thread.last_updated_date = datetime.now().isoformat()
                    await session.commit()
            except Exception as e:
                await session.rollback()
                raise e

    async def list_messages(self, thread_id: int, hide_tool_msgs: bool = False) -> List[Dict[str, Any]]:
        async with self.db.get_async_session() as session:
            thread = await session.get(Thread, thread_id)
            if not thread:
                return []
            messages = json.loads(thread.messages)
            if hide_tool_msgs:
                return [msg for msg in messages if msg.get('role') != 'tool']
            return messages
        
    async def cleanup_incomplete_tool_calls(self, thread_id: int):
        messages = await self.list_messages(thread_id)
        last_assistant_message = next((m for m in reversed(messages) if m['role'] == 'assistant' and 'tool_calls' in m), None)
        
        if last_assistant_message:
            tool_calls = last_assistant_message.get('tool_calls', [])
            tool_responses = [m for m in messages[messages.index(last_assistant_message)+1:] if m['role'] == 'tool']
            
            if len(tool_calls) != len(tool_responses):
                # Remove the incomplete assistant message and all subsequent messages
                messages = messages[:messages.index(last_assistant_message)]
                
                async with self.db.get_async_session() as session:
                    thread = await session.get(Thread, thread_id)
                    if thread:
                        thread.messages = json.dumps(messages)
                        await session.commit()
                
                return True
        return False
        
    async def run_thread(self, thread_id: int, system_message: Dict[str, Any], model_name: Any, json_mode: bool = False, temperature: int = 0, max_tokens: Optional[Any] = None, tools: Optional[List[str]] = None, tool_choice: str = "auto", additional_instructions: Optional[str] = None) -> Any:
        if await self.should_stop(thread_id):
            return {"status": "stopped", "message": "Session cancelled"}

        messages = await self.list_messages(thread_id)
        temp_messages = [system_message] + messages

        if additional_instructions:
            temp_messages.append({
                "role": "system",
                "content": f"{additional_instructions}"
            })

        try:
            if tools is None:
                tools = list(self.tool_registry.get_all_tools().values())
            
            # Format tools correctly
            formatted_tools = []
            for tool in tools:
                if isinstance(tool, Tool):
                    formatted_tools.extend(tool.schema())
                elif isinstance(tool, dict):
                    formatted_tools.append(tool)
                else:
                    raise ValueError(f"Invalid tool type: {type(tool)}")

            response = await make_llm_api_call(temp_messages, model_name, json_mode, temperature, max_tokens, formatted_tools, tool_choice)
        except Exception as e:
            logging.error(f"Error in API call: {str(e)}")
            return {"status": "error", "message": f"API call failed: {str(e)}"}

        if tools is None:
            response_content = response.choices[0].message['content']
            await self.add_message(thread_id, {"role": "assistant", "content": response_content})
        else:
            try:
                response_message = response.choices[0].message
                tool_calls = response_message.get('tool_calls', [])
                
                if tool_calls:
                    assistant_message = {
                        "role": "assistant",
                        "content": response_message.get('content') or "",
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": tool_call.function.arguments
                                }
                            } for tool_call in tool_calls
                        ]
                    }
                    await self.add_message(thread_id, assistant_message)

                    for tool_call in tool_calls:
                        function_name = tool_call.function.name
                        tool_instance = self.tool_registry.get_tool(function_name)
                        function_to_call = getattr(tool_instance, function_name)
                        function_args = json.loads(tool_call.function.arguments)
                        print(f"Function arguments for {function_name}:", function_args)
                        try:
                            function_response = await function_to_call(**function_args)
                                                        
                        except Exception as e:
                            error_message = f"Error in {function_name}: {str(e)}"
                            function_response = ToolResult(success=False, output=error_message)
                        
                        tool_message = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": function_name,
                            "content": str(function_response),
                        }
                        await self.add_message(thread_id, tool_message)
                        
                    
                    if await self.should_stop(thread_id):
                        return {"status": "stopped", "message": "Session cancelled after tool execution"}

            
            except AttributeError as e:
                logging.error(f"AttributeError: {e}")
                response_content = response.choices[0].message['content']
                await self.add_message(thread_id, {"role": "assistant", "content": response_content or ""})

        if await self.should_stop(thread_id):
            return {"status": "stopped", "message": "Session cancelled"}

        await self.save_thread_run(thread_id)

        return response

    async def should_stop(self, thread_id: int) -> bool:
        async with self.db.get_async_session() as session:
            stmt = select(ThreadRun).where(ThreadRun.thread_id == thread_id, ThreadRun.status.in_(['stopping', 'cancelled', 'paused'])).order_by(ThreadRun.run_id.desc()).limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none() is not None

    async def save_thread_run(self, thread_id: int):
        async with self.db.get_async_session() as session:
            thread = await session.get(Thread, thread_id)
            if not thread:
                raise ValueError(f"Thread with id {thread_id} not found")

            messages = json.loads(thread.messages)
            working_memory_state = await self.working_memory.export_memory(thread_id)
            creation_date = datetime.now().isoformat()
            
            new_thread_run = ThreadRun(
                thread_id=thread_id,
                messages=json.dumps(messages),
                creation_date=creation_date,
                working_memory=json.dumps(working_memory_state),
                status='completed'
            )
            session.add(new_thread_run)
            await session.commit()

    async def get_thread(self, thread_id: int) -> Optional[Thread]:
        async with self.db.get_async_session() as session:
            return await session.get(Thread, thread_id)

if __name__ == "__main__":
    pass