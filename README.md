# Charybdis

Evaluation of Hyperliquid HIP-3 builder-deployed perp markets for a potential
market-making (or other) strategy. **Phase A is research-only**: public
read-only data, no order placement, no wallet code, no keys.

- Spec: `docs/superpowers/specs/2026-07-04-hip3-market-evaluation-spec.md`
- Sibling project: `../sortilex` (Kalshi) — methodology source
  (executable quotes, clustered CIs, no look-ahead, disk/memory discipline);
  no code imports across repos.

Data lives under `data/` (git-ignored). Reports under `docs/reports/`.

## Research console

Interactive dashboard over `data/reports/*.parquet`.

```bash
cd console && npm install && npm run build && cd ..   # first time / after frontend changes
uv run charybdis-console                              # serves http://localhost:8787
```

Frontend development: `uv run charybdis-console` in one shell, `cd console && npm run dev` in another (Vite proxies `/api`).
