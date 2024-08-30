import json
import streamlit as st
import asyncio
from db import Database
from message_thread_manager import MessageThreadManager
from sqlalchemy import text
from tools.tool_registry import ToolRegistry
from working_memory_manager import WorkingMemory

# Initialize the database, message thread manager, tool registry, and working memory
db = Database()
thread_manager = MessageThreadManager(db)
tool_registry = ToolRegistry()
working_memory = WorkingMemory(db)

async def get_all_threads():
    async with db.get_async_session() as session:
        result = await session.execute(
            text("SELECT thread_id, creation_date FROM threads ORDER BY creation_date DESC")
        )
        return result.fetchall()

async def create_new_thread():
    return await thread_manager.create_thread()

async def run_thread(thread_id, system_message, model_name, json_mode=False, temperature=0, max_tokens=None, tools=None, tool_choice="auto", additional_instructions=None):
    response = await thread_manager.run_thread(thread_id, system_message, model_name, json_mode, temperature, max_tokens, tools, tool_choice, additional_instructions)
    return response

async def add_message(thread_id, role, content):
    await thread_manager.add_message(thread_id, {"role": role, "content": content})

async def get_message(thread_id, message_index):
    return await thread_manager.get_message(thread_id, message_index)

async def modify_message(thread_id, message_index, new_content):
    message = await get_message(thread_id, message_index)
    if message:
        message['content'] = new_content
        await thread_manager.modify_message(thread_id, message_index, message)

async def remove_message(thread_id, message_index):
    await thread_manager.remove_message(thread_id, message_index)


def main():
    st.set_page_config(layout="wide")
  
    # Sidebar for thread selection and creation
    with st.sidebar:
        st.title("Threads")
        if st.button("New Thread"):
            new_thread_id = asyncio.run(create_new_thread())
            st.session_state.selected_thread = new_thread_id
            st.rerun()
        
        threads = asyncio.run(get_all_threads())
        for thread in threads:
            if st.button(f"Thread {thread.thread_id}", key=f"thread_{thread.thread_id}"):
                st.session_state.selected_thread = thread.thread_id
                st.rerun()

    # Main chat area
    if hasattr(st.session_state, 'selected_thread'):
        thread_id = st.session_state.selected_thread
        st.header(f"Thread {thread_id}")

        # Chat messages display
        messages = asyncio.run(thread_manager.list_messages(thread_id))
        for index, msg in enumerate(messages):
            with st.chat_message(msg['role']):
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.write(msg['content'])
                with col2:
                    if st.button("Edit", key=f"edit_{index}"):
                        st.session_state.editing_message = index
                        st.rerun()

            if hasattr(st.session_state, 'editing_message') and st.session_state.editing_message == index:
                new_content = st.text_area("Edit message:", value=msg['content'], key=f"edit_area_{index}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Save", key=f"save_{index}"):
                        asyncio.run(modify_message(thread_id, index, new_content))
                        del st.session_state.editing_message
                        st.rerun()
                with col2:
                    if st.button("Cancel", key=f"cancel_{index}"):
                        del st.session_state.editing_message
                        st.rerun()
    
        # Thread settings
        with st.expander("Agent Settings", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                system_instructions = st.text_area("System Instructions:", value="You are a helpful assistant.")
                model_name = st.selectbox("Model:", ["gpt-4o", "anthropic/claude-3-5-sonnet-20240620"])
                temperature = st.slider("Temperature:", min_value=0.0, max_value=2.0, value=0.0, step=0.1)
                max_tokens = st.number_input("Max Tokens:", min_value=1, value=None)
                json_mode = st.checkbox("JSON Mode")
            with col2:
                available_tools = list(tool_registry.get_all_tools().keys())
                tools = st.multiselect("Tools:", available_tools)
                tool_choice = st.selectbox("Tool Choice:", ["auto", "none", "required"] + tools)
                additional_instructions = st.text_area("Additional Instructions:")

    # Input area
        with st.container():
            col1, col2 = st.columns([4, 1])
            with col1:
                user_input = st.text_input("Enter your message:", key="user_input")
            with col2:
                role = st.selectbox("Role:", ["user", "assistant"])

            col3, col4 = st.columns(2)
            with col3:
                if st.button("Add", use_container_width=True):
                    if user_input:
                        asyncio.run(add_message(thread_id, role, user_input))
                        st.rerun()
            with col4:
                if st.button("Run", use_container_width=True):
                    system_message = {"role": "system", "content": system_instructions}
                    selected_tools = [tool_registry.get_tool(tool).schema()[0] for tool in tools] if tools else None
                    response = asyncio.run(run_thread(
                        thread_id,
                        system_message,
                        model_name=model_name,
                        json_mode=json_mode,
                        temperature=temperature,
                        max_tokens=max_tokens if max_tokens else None,
                        tools=selected_tools,
                        tool_choice=tool_choice,
                        additional_instructions=additional_instructions if additional_instructions else None
                    ))
                    asyncio.run(add_message(thread_id, "assistant", response.choices[0].message['content']))
                    st.rerun()



        # Working Memory Management
        with st.expander("Agent Working Memory", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                module_name = st.text_input("Module Name:")
                module_data = st.text_area("Module Data (JSON):")
                if st.button("Add/Update Module"):
                    if module_name and module_data:
                        try:
                            data = json.loads(module_data)
                            asyncio.run(working_memory.add_or_update_module(thread_id, module_name, data))
                            st.success(f"Module '{module_name}' added/updated successfully.")
                        except json.JSONDecodeError:
                            st.error("Invalid JSON data. Please check your input.")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")

                modules = asyncio.run(working_memory.get_modules(thread_id))
                selected_module = st.selectbox("Select Module:", [""] + modules)

                if selected_module:
                    col3, col4 = st.columns(2)
                    with col3:
                        if st.button("Get Module"):
                            data = asyncio.run(working_memory.get_module(thread_id, selected_module))
                            if data:
                                st.json(data)
                            else:
                                st.info(f"No data found for module '{selected_module}'.")
                    with col4:
                        if st.button("Delete Module"):
                            asyncio.run(working_memory.delete_module(thread_id, selected_module))
                            st.success(f"Module '{selected_module}' deleted successfully.")
                            st.rerun()

            with col2:
                if st.button("Export Memory"):
                    memory_structure = asyncio.run(working_memory.export_memory(thread_id))
                    st.json(memory_structure)

                if st.button("Clear Memory"):
                    asyncio.run(working_memory.clear_memory(thread_id))
                    st.success("Memory cleared successfully.")

if __name__ == "__main__":
    main()