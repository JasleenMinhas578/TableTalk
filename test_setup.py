from dotenv import load_dotenv
load_dotenv()

from langchain_ollama import ChatOllama
from langfuse.langchain import CallbackHandler

llm = ChatOllama(model="qwen2.5-coder:7b")
handler = CallbackHandler()

reply = llm.invoke(
    "Write a SQL query to count rows in a table called orders.",
    config={"callbacks": [handler]},
)
print(reply.content)