"""
Streamlit Chat App Template

A ready-to-use chat interface for conversational models using Streamlit.
Replace MODEL_ID with your model of choice.
"""

import streamlit as st
from huggingface_hub import InferenceClient

# ============================================================================
# CONFIGURATION - Modify these values
# ============================================================================
MODEL_ID = "HuggingFaceH4/zephyr-7b-beta"  # Change to your model
PAGE_TITLE = "Chat Assistant"
PAGE_ICON = "🤖"
WELCOME_MESSAGE = "Hello! I'm an AI assistant. How can I help you today?"

# ============================================================================
# PAGE SETUP
# ============================================================================
st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout="centered",
)

st.title(f"{PAGE_ICON} {PAGE_TITLE}")


# ============================================================================
# APPLICATION CODE
# ============================================================================
@st.cache_resource
def get_client():
    """Initialize the Hugging Face client (cached)."""
    return InferenceClient(MODEL_ID)


client = get_client()

# Sidebar for settings
with st.sidebar:
    st.header("Settings")
    system_message = st.text_area(
        "System Message",
        value="You are a helpful, harmless, and honest assistant.",
        height=100,
    )
    max_tokens = st.slider("Max Tokens", 50, 2048, 512)
    temperature = st.slider("Temperature", 0.1, 2.0, 0.7, 0.1)
    top_p = st.slider("Top-p", 0.1, 1.0, 0.95, 0.05)

    st.divider()
    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display welcome message if no history
if not st.session_state.messages:
    with st.chat_message("assistant"):
        st.markdown(WELCOME_MESSAGE)

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Handle user input
if prompt := st.chat_input("Type your message..."):
    # Add user message to history
    st.session_state.messages.append({"role": "user", "content": prompt})

    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate response
    with st.chat_message("assistant"):
        # Build messages for API
        messages = [{"role": "system", "content": system_message}]
        messages.extend(st.session_state.messages)

        # Stream the response
        with st.spinner("Thinking..."):
            response = client.chat_completion(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
            )
            reply = response.choices[0].message.content
            st.markdown(reply)

    # Add assistant response to history
    st.session_state.messages.append({"role": "assistant", "content": reply})
