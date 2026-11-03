"""Tests for ContextCompressor."""

import pytest
from hearthwren.context_compressor import ContextCompressor


def test_summarize_tool_output():
    compressor = ContextCompressor()

    # Dict output with long content
    dict_output = {
        "success": True,
        "path": "src/main.py",
        "content": "\n".join([f"line {i}" for i in range(1, 50)]),
    }
    summary = compressor.summarize_tool_output(dict_output, max_lines=5)
    assert "success=True" in summary
    assert "path=src/main.py" in summary
    assert "lines omitted" in summary
    assert "line 1" in summary


def test_compress_history():
    compressor = ContextCompressor()

    history = [
        ("How do I build?", "Run cargo build in root"),
        ("How do I test?", "Run cargo test in root"),
        ("What about lint?", "Run cargo clippy in root"),
        ("Can we add CI?", "Yes, configure github actions"),
    ]
    compressed = compressor.compress_history(history, max_turns=2)
    assert "[Earlier conversation summary]:" in compressed
    assert "User: Can we add CI?" in compressed
    assert "Assistant: Yes, configure github actions" in compressed


def test_assemble_budgeted_prompt_within_limit():
    compressor = ContextCompressor(context_ceiling=2000, reserve_completion_tokens=200)
    system = "You are Hearthwren."
    user = "Implement a sorting algorithm."
    extra = "Extra information about the environment." * 10
    memory = "AGENT_MEMORY excerpt: project is Hearthwren."

    sys_res, prompt_res = compressor.assemble_budgeted_prompt(
        system_prompt=system,
        user_message=user,
        memory_excerpt=memory,
        extra_context=extra,
    )

    total = compressor.estimator(sys_res) + compressor.estimator(prompt_res)
    assert total <= compressor.prompt_token_budget
    assert "Task: Implement a sorting algorithm." in prompt_res
    assert "You are Hearthwren." in sys_res


def test_assemble_budgeted_prompt_trims_lowest_priority_first():
    # Very small budget
    compressor = ContextCompressor(context_ceiling=200, reserve_completion_tokens=50)
    # Available budget: 150 tokens = ~600 chars
    system = "System prompt."
    user = "Task: Run tests."
    huge_extra = "EXTRA_DATA " * 200  # ~2200 chars (~550 tokens)
    memory = "KEY_MEMORY: project Hearthwren"

    sys_res, prompt_res = compressor.assemble_budgeted_prompt(
        system_prompt=system,
        user_message=user,
        memory_excerpt=memory,
        extra_context=huge_extra,
    )

    total = compressor.estimator(sys_res) + compressor.estimator(prompt_res)
    assert total <= compressor.prompt_token_budget
    # Extra data (lowest priority) should be trimmed or dropped
    assert "EXTRA_DATA " * 100 not in prompt_res
    # User task must remain
    assert "Task: Run tests." in prompt_res
