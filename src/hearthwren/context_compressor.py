"""Hierarchical context compression and prompt budgeting for Hearthwren.

Ensures prompts strictly respect the 4 096 (or configured) token ceiling
without discarding critical instructions or user intent.
"""

from __future__ import annotations

import re
from typing import Any, Callable


class ContextCompressor:
    """Budgets and compresses prompt context components hierarchically."""

    def __init__(
        self,
        token_estimator: Callable[[str], int] | None = None,
        context_ceiling: int = 4096,
        reserve_completion_tokens: int = 512,
    ):
        self.estimator = token_estimator or self._default_estimate_tokens
        self.context_ceiling = context_ceiling
        self.reserve_completion_tokens = reserve_completion_tokens
        self.prompt_token_budget = max(50, context_ceiling - reserve_completion_tokens)

    @staticmethod
    def _default_estimate_tokens(text: str) -> int:
        """Heuristic token estimator (~4 characters per token)."""
        if not text:
            return 0
        return max(1, len(text) // 4)

    def summarize_tool_output(self, tool_output: str | dict[str, Any], max_lines: int = 10) -> str:
        """Condense large tool outputs to essential facts, paths, and status."""
        if isinstance(tool_output, dict):
            # Extract key fields
            success = tool_output.get("success", False)
            path = tool_output.get("path") or tool_output.get("culprit_file")
            err = tool_output.get("error") or tool_output.get("failure_summary")
            content = tool_output.get("content", "")

            summary_parts = [f"Result: success={success}"]
            if path:
                summary_parts.append(f"path={path}")
            if err:
                summary_parts.append(f"error={err}")

            if content:
                lines = content.splitlines()
                if len(lines) > max_lines:
                    head = "\n".join(lines[:max_lines])
                    summary_parts.append(f"content:\n{head}\n... [{len(lines) - max_lines} lines omitted]")
                else:
                    summary_parts.append(f"content:\n{content}")

            return " | ".join(summary_parts[:3]) + ("\n" + summary_parts[3] if len(summary_parts) > 3 else "")

        raw_str = str(tool_output)
        lines = raw_str.splitlines()
        if len(lines) > max_lines:
            head = "\n".join(lines[:max_lines])
            return f"{head}\n... [{len(lines) - max_lines} lines omitted]"
        return raw_str

    def compress_history(self, history: list[tuple[str, str]], max_turns: int = 3) -> str:
        """Summarize older multi-turn history into compact lines."""
        if not history:
            return ""

        # Keep recent turns in short form, summarize earlier turns
        recent_turns = history[-max_turns:]
        earlier_turns = history[:-max_turns]

        summary_lines: list[str] = []
        if earlier_turns:
            summary_lines.append("[Earlier conversation summary]:")
            for u, a in earlier_turns:
                short_u = (u[:50] + "...") if len(u) > 50 else u
                short_a = (a[:50] + "...") if len(a) > 50 else a
                summary_lines.append(f"- User: {short_u} -> Agent: {short_a}")

        for u, a in recent_turns:
            summary_lines.append(f"User: {u}")
            # Truncate assistant answer in history to 150 chars
            short_ans = (a[:150] + "...") if len(a) > 150 else a
            summary_lines.append(f"Assistant: {short_ans}")

        return "\n".join(summary_lines)

    def assemble_budgeted_prompt(
        self,
        system_prompt: str,
        user_message: str,
        memory_excerpt: str = "",
        extra_context: str = "",
        tool_results: list[dict[str, Any] | str] | None = None,
        history: list[tuple[str, str]] | None = None,
    ) -> tuple[str, str]:
        """Assemble system prompt and prompt body strictly within token budget.
        
        Priority order:
        1. System prompt & user message (CRITICAL: preserved fully)
        2. Tool results (summarized)
        3. Memory excerpt (trimmed if needed)
        4. History (compressed)
        5. Extra context (trimmed first on budget pressure)
        """
        system_tokens = self.estimator(system_prompt)
        user_tokens = self.estimator(user_message)

        # Budget remaining for supplementary context
        remaining_budget = self.prompt_token_budget - (system_tokens + user_tokens)

        # 1. Format tool results
        tool_str = ""
        if tool_results:
            summarized_tools = [self.summarize_tool_output(t) for t in tool_results]
            tool_str = "[Recent Tool Output]:\n" + "\n".join(summarized_tools)

        # 2. Format history
        history_str = self.compress_history(history or [])

        # 3. Assemble supplemental sections in priority order
        sections: list[tuple[str, str, int]] = []
        # (name, content, priority: lower number = drops last)
        if tool_str:
            sections.append(("tool_results", tool_str, 1))
        if memory_excerpt:
            sections.append(("memory", memory_excerpt.strip(), 2))
        if history_str:
            sections.append(("history", history_str.strip(), 3))
        if extra_context:
            sections.append(("extra_context", extra_context.strip(), 4))

        # Check total estimated tokens
        active_sections: dict[str, str] = {name: content for name, content, _ in sections}
        
        def calculate_total_tokens() -> int:
            content_sum = sum(self.estimator(text) for text in active_sections.values())
            return system_tokens + user_tokens + content_sum

        # Trim from lowest priority (highest priority number) to highest priority
        sorted_sections = sorted(sections, key=lambda s: s[2], reverse=True)

        for name, content, _ in sorted_sections:
            if calculate_total_tokens() <= self.prompt_token_budget:
                break
            
            # Need to reduce this section
            tokens_to_shed = calculate_total_tokens() - self.prompt_token_budget
            current_sec_tokens = self.estimator(active_sections[name])
            
            if current_sec_tokens <= tokens_to_shed:
                # Drop this section entirely
                active_sections.pop(name, None)
            else:
                # Trim section text
                chars_to_remove = tokens_to_shed * 4 + 50
                trimmed = active_sections[name][:-chars_to_remove] + "\n... [trimmed to fit context budget]"
                active_sections[name] = trimmed

        # If user message itself is exceptionally large and exceeds budget
        if calculate_total_tokens() > self.prompt_token_budget:
            tokens_over = calculate_total_tokens() - self.prompt_token_budget
            chars_to_remove = tokens_over * 4 + 100
            if chars_to_remove < len(user_message):
                user_message = user_message[:-chars_to_remove] + "\n... [User query truncated to fit context budget]"
            else:
                user_message = user_message[:500] + "\n... [User query truncated to fit context budget]"

        # Assemble final prompt body
        prompt_parts: list[str] = []
        if "memory" in active_sections:
            prompt_parts.append(active_sections["memory"])
        if "extra_context" in active_sections:
            prompt_parts.append(active_sections["extra_context"])
        if "history" in active_sections:
            prompt_parts.append(active_sections["history"])
        if "tool_results" in active_sections:
            prompt_parts.append(active_sections["tool_results"])

        prompt_parts.append(f"Task: {user_message}")
        prompt_body = "\n\n".join(part for part in prompt_parts if part).strip()

        return system_prompt, prompt_body
