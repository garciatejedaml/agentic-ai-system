"""
Entry point for the Agentic AI System POC.

Usage:
    # Interactive mode
    python main.py

    # Single query
    python main.py "What is LangGraph?"

    # With debug output
    LANGGRAPH_DEBUG=true python main.py "How do Strands agents work?"
"""
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from src.config import config

console = Console()


def run_single(query: str) -> None:
    """Run one query and print the result."""
    config.validate()

    from src.graph.workflow import run_query

    console.print(f"\n[bold cyan]Query:[/bold cyan] {query}\n")

    with console.status("[bold green]Running agentic pipeline..."):
        state = run_query(query)

    response = state.get("final_response") or "No response generated."

    console.print(Panel(Markdown(response), title="[bold]Response[/bold]", border_style="green"))

    if config.LANGGRAPH_DEBUG:
        console.rule("[dim]Debug info[/dim]")
        rag_docs = state.get("rag_context") or []
        console.print(f"[dim]RAG docs retrieved: {len(rag_docs)}[/dim]")
        if state.get("research"):
            console.print(f"[dim]Research length: {len(state['research'])} chars[/dim]")


def interactive_mode() -> None:
    """Simple REPL for interactive testing."""
    config.validate()

    console.print(
        Panel(
            "[bold]Agentic AI System POC[/bold]\n"
            f"Provider: [cyan]{config.LLM_PROVIDER}[/cyan]  "
            f"Model: [cyan]{config.ANTHROPIC_MODEL if config.is_local() else config.BEDROCK_MODEL}[/cyan]\n"
            "Type [bold red]exit[/bold red] or [bold red]quit[/bold red] to stop.",
            border_style="blue",
        )
    )

    from src.graph.workflow import run_query

    while True:
        try:
            query = console.input("\n[bold yellow]You:[/bold yellow] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye![/dim]")
            break

        if query.lower() in {"exit", "quit", "q"}:
            console.print("[dim]Bye![/dim]")
            break

        if not query:
            continue

        with console.status("[bold green]Thinking..."):
            state = run_query(query)

        response = state.get("final_response") or "No response generated."
        console.print(Panel(Markdown(response), title="[bold]Agent[/bold]", border_style="green"))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_single(" ".join(sys.argv[1:]))
    else:
        interactive_mode()
