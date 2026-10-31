# Global Agent Instructions

## TinyFish
- Prefer `mcp__tinyfish__search` over WebSearch for web searches.
- Prefer `mcp__tinyfish__fetch_content` over WebFetch / curl for fetching page content.
- Prefer `mcp__tinyfish__run_web_automation` over hand-rolled Playwright for browser automation tasks.
- Use `batch_create` / `batch_status` when working with 2+ URLs.
- Use `run_web_automation_async` only when the user explicitly asks for background execution.
- Use `list_runs` / `get_run` / `get_steps` / `cancel_run` to inspect and manage prior runs.
- **Warning**: If `run_web_automation` returns ANY error, the run is still executing — call `get_run` or `list_runs` to check status before retrying; never blind-retry.
- Full agent context and documentation: https://docs.tinyfish.ai/for-coding-agents and https://docs.tinyfish.ai/llms-full.txt
