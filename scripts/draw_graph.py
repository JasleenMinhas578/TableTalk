from pathlib import Path

from app.agent.sql_agent import sql_agent

docs = Path("docs")
docs.mkdir(exist_ok=True)

mermaid = sql_agent.get_graph().draw_mermaid()
(docs / "sql_agent_graph.md").write_text(f"# SQL agent graph\n\n```mermaid\n{mermaid}\n```\n")

print("Saved docs/sql_agent_graph.md")