"""
Tool Registry — gives agents real capabilities beyond just LLM calls.
Each tool is a callable with a name, description, and parameter schema.
"""
from __future__ import annotations
import ast
import json
import math
import re
import subprocess
import textwrap
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import requests
import logging

logger = logging.getLogger(__name__)


class Tool:
    """A single tool that an agent can invoke."""

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable[..., str],
        parameters: Dict[str, str],
    ):
        self.name = name
        self.description = description
        self.func = func
        self.parameters = parameters  # param_name -> description

    def run(self, **kwargs: Any) -> str:
        """Execute the tool and return string output."""
        try:
            result = self.func(**kwargs)
            return str(result)
        except Exception as exc:
            logger.error("Tool '%s' failed: %s", self.name, exc)
            return f"[ERROR] Tool '{self.name}' failed: {exc}"

    def to_prompt_description(self) -> str:
        """Format this tool for inclusion in an agent's system prompt."""
        params_str = "\n".join(f"  - {k}: {v}" for k, v in self.parameters.items())
        return (
            f"Tool: {self.name}\n"
            f"Description: {self.description}\n"
            f"Parameters:\n{params_str}"
        )


# ─────────────────────────────── Tool implementations ────────────────────────

def _web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo's instant-answer API (no key required)."""
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        results = []
        if data.get("AbstractText"):
            results.append(f"Summary: {data['AbstractText']}")
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"• {topic['Text']}")

        if not results:
            return f"No instant results found for '{query}'. Try rephrasing."
        return f"Search results for '{query}':\n" + "\n".join(results)
    except Exception as exc:
        return f"Web search failed: {exc}"


def _calculate(expression: str) -> str:
    """Safely evaluate a mathematical expression."""
    allowed_names = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
    allowed_names.update({"abs": abs, "round": round, "min": min, "max": max, "sum": sum})
    try:
        # AST-based safe eval
        tree = ast.parse(expression, mode="eval")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = node.func.id if isinstance(node.func, ast.Name) else None
                if func_name and func_name not in allowed_names:
                    return f"[ERROR] Function '{func_name}' is not allowed."
        result = eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, allowed_names)
        return f"{expression} = {result}"
    except Exception as exc:
        return f"[ERROR] Could not evaluate '{expression}': {exc}"


def _get_current_datetime(timezone: str = "UTC") -> str:
    """Return the current date and time."""
    now = datetime.utcnow()
    return f"Current UTC datetime: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}"


def _summarize_text(text: str, max_words: int = 150) -> str:
    """Extract the first `max_words` words as a quick summary."""
    words = text.split()
    if len(words) <= max_words:
        return text
    snippet = " ".join(words[:max_words])
    return snippet + "..."


def _fetch_url(url: str) -> str:
    """Fetch the text content of a URL."""
    try:
        headers = {"User-Agent": "MultiAgentBot/1.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        # Strip HTML tags naively
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:3000] + ("..." if len(text) > 3000 else "")
    except Exception as exc:
        return f"[ERROR] Could not fetch URL: {exc}"


def _json_format(data: str) -> str:
    """Pretty-print a JSON string."""
    try:
        parsed = json.loads(data)
        return json.dumps(parsed, indent=2)
    except Exception:
        return f"[ERROR] Invalid JSON: {data[:200]}"


# ─────────────────────────────── Registry ────────────────────────────────────

class ToolRegistry:
    """Central registry of all available tools."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register all built-in tools."""
        defaults = [
            Tool(
                name="web_search",
                description="Search the web for current information on a topic.",
                func=_web_search,
                parameters={"query": "The search query string", "max_results": "Max number of results (default 5)"},
            ),
            Tool(
                name="calculate",
                description="Evaluate a mathematical expression safely.",
                func=_calculate,
                parameters={"expression": "A valid Python math expression, e.g. '2 ** 10 + sqrt(144)'"},
            ),
            Tool(
                name="get_datetime",
                description="Get the current date and time in UTC.",
                func=_get_current_datetime,
                parameters={"timezone": "Timezone name (default: UTC)"},
            ),
            Tool(
                name="summarize_text",
                description="Shorten a long piece of text to a brief summary.",
                func=_summarize_text,
                parameters={"text": "The full text to summarize", "max_words": "Max words in summary (default 150)"},
            ),
            Tool(
                name="fetch_url",
                description="Fetch and return the text content of any public URL.",
                func=_fetch_url,
                parameters={"url": "The full URL to fetch"},
            ),
            Tool(
                name="json_format",
                description="Pretty-print a JSON string for readability.",
                func=_json_format,
                parameters={"data": "The raw JSON string"},
            ),
        ]
        for tool in defaults:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def run(self, name: str, **kwargs: Any) -> str:
        tool = self.get(name)
        if not tool:
            return f"[ERROR] Unknown tool '{name}'. Available: {self.list_names()}"
        return tool.run(**kwargs)

    def list_names(self) -> List[str]:
        return list(self._tools.keys())

    def to_system_prompt_block(self) -> str:
        """Return a formatted block listing all tools for injection into a system prompt."""
        lines = ["## Available Tools\n"]
        for tool in self._tools.values():
            lines.append(tool.to_prompt_description())
            lines.append("")
        lines.append(
            "To use a tool, include this JSON block in your response:\n"
            '```tool_call\n{"tool": "<tool_name>", "args": {<key>: <value>}}\n```\n'
            "Wait for the tool result before continuing your response."
        )
        return "\n".join(lines)


# Singleton registry shared across the application
tool_registry = ToolRegistry()
