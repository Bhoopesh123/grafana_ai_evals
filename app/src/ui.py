import streamlit as st

from src.generation import answer


st.set_page_config(page_title="Grafana AI Evaluations", page_icon="📊")
st.title("Grafana AI Evaluations")
st.caption("OpenAI traffic with asynchronous evaluation across ten quality and safety pillars")

if "messages" not in st.session_state:
    st.session_state.messages = []
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask about the local LGTM or evaluation demo"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        output = ""
        try:
            metadata = {}
            for event in answer(prompt):
                if event["type"] == "token":
                    output += event["value"]
                    placeholder.markdown(output + "▌")
                else:
                    metadata = event
            placeholder.markdown(output)
            st.caption(f"Request `{metadata['request_id']}` · trace `{metadata['trace_id']}` · 10-pillar evaluation queued")
        except Exception as exc:
            output = f"Request failed: {exc}"
            st.error(output)
    st.session_state.messages.append({"role": "assistant", "content": output})
