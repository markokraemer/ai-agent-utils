import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from db import Database, MemoryModule
from sqlalchemy.exc import IntegrityError
from asyncio import Lock
from contextlib import asynccontextmanager

class WorkingMemory:
    def __init__(self, db: Database):
        self.db = db
        self.lock = Lock()
        # logging.info("WorkingMemory initialized")

    @asynccontextmanager
    async def session_scope(self):
        async with self.db.get_async_session() as session:
            try:
                yield session
                await session.commit()
                logging.debug("Session committed successfully")
            except:
                await session.rollback()
                logging.error("Session rollback due to error", exc_info=True)
                raise

    async def add_or_update_module(self, thread_id: int, module_name: str, data: dict):
        async with self.lock:
            async with self.session_scope() as session:
                try:
                    stmt = select(MemoryModule).filter_by(
                        thread_id=thread_id, module_name=module_name
                    ).with_for_update()
                    result = await session.execute(stmt)
                    memory_module = result.scalar_one_or_none()

                    if memory_module:
                        memory_module.data = json.dumps(data)
                        logging.info(f"Updated module: {module_name} for thread: {thread_id}")
                    else:
                        new_module = MemoryModule(
                            thread_id=thread_id,
                            module_name=module_name,
                            data=json.dumps(data)
                        )
                        session.add(new_module)
                        logging.info(f"Added new module: {module_name} for thread: {thread_id}")
                    await session.flush()
                except IntegrityError:
                    logging.error(f"IntegrityError while adding/updating module: {module_name}", exc_info=True)
                    raise

    async def get_module(self, thread_id: int, module_name: str):
        async with self.session_scope() as session:
            stmt = select(MemoryModule).filter_by(
                thread_id=thread_id, module_name=module_name
            )
            result = await session.execute(stmt)
            memory_module = result.scalar_one_or_none()
            if memory_module:
                logging.info(f"Retrieved module: {module_name} for thread: {thread_id}")
                return json.loads(memory_module.data)
            else:
                logging.info(f"Module not found: {module_name} for thread: {thread_id}")
                return None

    async def delete_module(self, thread_id: int, module_name: str):
        async with self.lock:
            async with self.session_scope() as session:
                stmt = select(MemoryModule).filter_by(
                    thread_id=thread_id, module_name=module_name
                ).with_for_update()
                result = await session.execute(stmt)
                memory_module = result.scalar_one_or_none()
                if memory_module:
                    await session.delete(memory_module)
                    logging.info(f"Deleted module: {module_name} for thread: {thread_id}")
                else:
                    logging.info(f"Module not found for deletion: {module_name} for thread: {thread_id}")

    async def export_memory(self, thread_id: int):
        async with self.session_scope() as session:
            stmt = select(MemoryModule).filter_by(thread_id=thread_id)
            result = await session.execute(stmt)
            memory_modules = result.scalars().all()
            memory_structure = {}
            for module in memory_modules:
                memory_structure[module.module_name] = json.loads(module.data)
            logging.info(f"Exported memory for thread: {thread_id}")
            return memory_structure

    async def clear_memory(self, thread_id: int):
        async with self.lock:
            async with self.session_scope() as session:
                stmt = select(MemoryModule).filter_by(thread_id=thread_id)
                result = await session.execute(stmt)
                memory_modules = result.scalars().all()
                for module in memory_modules:
                    await session.delete(module)
                logging.info(f"Cleared memory for thread: {thread_id}")

    async def get_modules(self, thread_id: int):
        async with self.session_scope() as session:
            stmt = select(MemoryModule.module_name).filter_by(thread_id=thread_id)
            result = await session.execute(stmt)
            modules = result.scalars().all()
            logging.info(f"Retrieved module names for thread: {thread_id}")
            return modules