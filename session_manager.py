import os
import json
import asyncio
from typing import Any, Dict, List
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db import Database, Thread, ThreadRun

from message_thread_manager import MessageThreadManager
from working_memory_manager import WorkingMemory
from tools.tool_registry import ToolRegistry  

import logging

logging.basicConfig(level=logging.INFO)

class Session:
    def __init__(self):
        load_dotenv()
        self.db = Database()
        self.working_memory = WorkingMemory(self.db)
        self.thread_manager = MessageThreadManager(self.db)
        self.thread_id = None
        self.running = False
        self.stop_event = asyncio.Event()
        self.tool_registry = ToolRegistry()
        self.example_tool = self.tool_registry.get_tool("example_function")
        self.iteration_count = 0

    async def init_session(self, thread_id: int | None, objective: str, objective_images: List[Dict[str, Any]]):
        if thread_id is None:
            self.thread_id = await self.thread_manager.create_thread()
        else:
            self.thread_id = thread_id

        await self.thread_manager.cleanup_incomplete_tool_calls(self.thread_id)

        await self.thread_manager.add_message(self.thread_id, {"role": "user", "content": objective})
        
        await self.working_memory.clear_memory(self.thread_id)
        
        await self.working_memory.add_or_update_module(self.thread_id, "key", "value")

        logging.info(f"Agent session initialization complete for thread_id: {self.thread_id}")

    async def run_session(self, max_iterations: int | None = None):
        try:
            await self.thread_manager.cleanup_incomplete_tool_calls(self.thread_id)
            
            while not self.stop_event.is_set():
                logging.info(f"Starting iteration {self.iteration_count + 1} in run_session")
                
                # Check if the session should stop
                if await self.thread_manager.should_stop(self.thread_id):
                    logging.info("Session stop requested, breaking the loop")
                    break

                additional_instructions = f"Working Memory <working_memory> {json.dumps(await self.working_memory.export_memory(), indent=3)} </working_memory>"
                agent_instructions = "" 
                agent_continue_instructions = ""

                await self.thread_manager.run_thread(
                    self.thread_id, 
                    {"role": "system", "content": agent_instructions}, 
                    model_name="anthropic/claude-3-5-sonnet-20240620",
                    temperature=0.1,
                    tools=self.tools,
                    additional_instructions=additional_instructions,
                    tool_choice="auto",
                    max_tokens=8192
                )

                logging.info("Thread run completed") 

                self.iteration_count += 1

                if max_iterations and self.iteration_count >= max_iterations:
                    logging.info(f"Reached maximum iterations ({max_iterations}), ending session")
                    break

                # Add agent_continue_instructions if there are more iterations
                if self.iteration_count > 0 and (max_iterations is None or self.iteration_count < max_iterations):
                    await self.thread_manager.add_message(self.thread_id, {"role": "user", "content": agent_continue_instructions})

                await asyncio.sleep(0.1)
                
                if self.stop_event.is_set():
                    logging.info("Stop event detected, ending session")
                    break

        except Exception as e:
            logging.exception(f"Error in session: {str(e)}")
        finally:
            self.running = False
            self.thread_manager.save_thread_run(self.thread_id)

if __name__ == "__main__":
    pass