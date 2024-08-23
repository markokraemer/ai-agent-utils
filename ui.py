import streamlit as st
import asyncio
from db import Database
from message_thread_manager import MessageThreadManager
from sqlalchemy import text
from tools.tool_registry import ToolRegistry

# Initialize the database, message thread manager, and tool registry
db = Database()
thread_manager = MessageThreadManager(db)
tool_registry = ToolRegistry()

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
        st.title("Thread Manager")
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
        
        # Thread settings
        with st.expander("Agent Settings", expanded=False):
            col1, col2 = st.columns(2)
            with col1:
                system_instructions = st.text_area("System Instructions:", value="You are a helpful assistant.")
                model_name = st.selectbox("Model:", ["gpt-3.5-turbo", "gpt-4", "gpt-4-32k"])
                temperature = st.slider("Temperature:", min_value=0.0, max_value=2.0, value=0.0, step=0.1)
                max_tokens = st.number_input("Max Tokens:", min_value=1, value=None)
                json_mode = st.checkbox("JSON Mode")
            with col2:
                available_tools = list(tool_registry.get_all_tools().keys())
                tools = st.multiselect("Tools:", available_tools)
                tool_choice = st.selectbox("Tool Choice:", ["auto", "none", "required"] + tools)
                additional_instructions = st.text_area("Additional Instructions:")

        # Chat messages display
        messages = asyncio.run(thread_manager.list_messages(thread_id))
        for msg in messages:
            with st.chat_message(msg['role']):
                st.write(msg['content'])

        # Input area
        with st.container():
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            with col1:
                user_input = st.text_input("Enter your message:", key="user_input")
            with col2:
                role = st.selectbox("Role:", ["user", "assistant"])
            with col3:
                if st.button("Add"):
                    if user_input:
                        asyncio.run(add_message(thread_id, role, user_input))
                        st.rerun()
            with col4:
                if st.button("Run"):
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

if __name__ == "__main__":
    main()