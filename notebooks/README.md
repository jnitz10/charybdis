# Notebooks

## Start

```bash
uv run jupyter lab
```

Open `notebooks/00_explore.ipynb`. The kernel is the project venv, so
`charybdis.*` modules and polars are importable directly.

## Claude Code inside JupyterLab (Notebook Intelligence)

[notebook-intelligence](https://github.com/plmbr/notebook-intelligence) (NBI)
is installed as a dev dependency. One-time setup:

1. In JupyterLab, open the NBI chat panel (sparkle icon in the left sidebar).
2. Click the gear (settings) icon in the chat panel.
3. Set the provider to **Claude** → enables *Claude mode*, which launches your
   local Claude Code CLI for chat. You get Claude Code's full toolset, skills,
   MCP servers, and this project's context inside JupyterLab. Requires the
   `claude` CLI to be installed and logged in (it is, if you're reading this).
4. Optional: inline tab-completions use the Anthropic API directly — set
   `ANTHROPIC_API_KEY` in your environment before launching if you want them.

Settings persist in `~/.jupyter/nbi/config.json`.

Usage: type what you want in the chat ("load the funding census and plot APR
vs half-life") — NBI's agent can create and edit notebook cells directly.

## Conventions

- Notebooks are exploratory scratch space; anything worth keeping graduates
  into `charybdis/` modules with tests.
- `.ipynb_checkpoints/` is gitignored; commit notebooks only when the outputs
  are worth preserving.
