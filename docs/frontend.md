# Frontend

React 19 · Vite · TypeScript · Tailwind 4 · TanStack Query 5 · react-router 7 · react-force-graph-2d · react-markdown.

```
frontend/src/
├── api/
│   ├── types.ts      mirrors backend/schemas.py (kept in sync by hand)
│   ├── client.ts     fetch wrapper → ApiError(status, detail); one function per endpoint
│   └── hooks.ts      TanStack hooks; useInvestigation / useAsk implement POST → poll
├── lib/
│   ├── format.ts     money · timestamps · band → Tailwind class map
│   └── theme.tsx     ThemeProvider, useTheme, chartColors (canvas/SVG colours)
├── components/
│   ├── ui.tsx        Card · Stat · BandPill · SourceTag · Button · ErrorBox · Empty · Skeleton · Kv · Icon
│   ├── Layout.tsx    header (logo · nav · system pill · theme toggle) + footer
│   ├── BandCards · AlertTable · Pagination
│   ├── ShapChart · RulesList · MoneyFlowTable · CounterpartyTable
│   ├── InvestigationPanel · ReportView
│   ├── ForceGraph    canvas renderer (shared by account page and mini graph)
│   ├── MiniGraph     1-hop around both parties of an alert, two /graph calls merged
│   └── DailyAlertsChart   stacked SVG bars, log/linear, table view, tooltip
└── pages/  QueuePage · AlertDetailPage · AccountGraphPage (lazy) · OverviewPage · AskPage
```

## Screens

| Route | What it does |
|---|---|
| `/` | Queue. Band cards toggle filters; filters, sort and page live in the URL (`/?band=HIGH&sort=-amount_usd&page=3`). Default view excludes CLEAR. |
| `/alerts/:id` | Case file. Header tiles (score + anomaly percentile, disposition, pattern rules, model numbers); Detail / SAR-draft tabs; sticky module rail; transaction, SHAP, rules, counterparties, money flow, Neo4j mini-graph, investigator narrative. |
| `/accounts/:id?hops=1\|2` | Account network. Alerts/outflow/inflow tiles, force graph with zoom controls, counterparties, cycles, shared-counterparty peers. Header stats can take ~30 s on hub accounts (`find_cycles`). |
| `/overview` | Risk overview. Stat tiles, alerts-per-day chart, precision by band, top-10 HIGH. |
| `/ask?txn=&account=` | Investigation agent. Question box, context chip, live job bar, answer + numbered tool trace with per-tool source tags and expandable JSON. |

## Data fetching

- One `QueryClient`; `staleTime` 60 s; **4xx is never retried** (a 404 will not change its mind), 5xx/network retried once.
- Alert list uses `placeholderData` so paging/sorting doesn't flash skeletons.
- `useInvestigation` and `useAsk` keep an `enabled` flag that flips after the POST succeeds — a disabled TanStack query does not poll, so `refetchInterval` alone was not enough.
- Skeletons for content; spinners only inside long-running buttons.

## Design tokens

Everything is a semantic token declared in `src/index.css` under `@theme` and overridden under `.dark`:

| Role | Tokens |
|---|---|
| Surfaces | `canvas` `card` `well` `hover` `line` `line-soft` |
| Text | `ink` `ink-2` `muted` `faint` |
| Accent | `primary` `primary-dark` `primary-tint` `primary-line` |
| Bands | `high` `medium` `low` `clear` — each with `-tint` and `-line` |
| Status / engines | `ok` `llm` `neo` (+ tints) |
| Misc | `tooltip` `on-tooltip` `shadow-card` `shadow-pop` |

Use them as normal Tailwind utilities (`bg-card`, `text-muted`, `border-high-line`). The band map in `lib/format.ts` (`BAND[band].text / bg / tint / line / rail / hex`) is the only place band colours are enumerated; `hex` is for canvas/SVG fills.

The palette came from a Google Stitch export ("AML Ledger" design system): `#F7F8FA` canvas, white 12 px cards, Inter + JetBrains Mono, pill badges, `#2563EB` primary.

## Dark mode

Class strategy (`@custom-variant dark (&:where(.dark, .dark *))`). `ThemeProvider` applies `.dark` to `<html>`; preference is stored in `localStorage["aml-theme"]`, otherwise follows `prefers-color-scheme` and reacts to OS changes. Header toggle switches; right-click it to return to "follow system". Canvas and SVG colours that Tailwind cannot reach come from `chartColors(theme)`.

## Source tags

`SourceTag` (`NEO4J` `XGBOOST` `SHAP` `RULES` `LLM` `ISOLATION FOREST` `FEATURE STORE` `GROUND TRUTH`) appears in card headers and on tool-trace rows so the origin of every number is visible. When adding a panel, pass `sources={[…]}` to `Card`.

## Commands

```bash
npm run dev       # http://localhost:5173 (strictPort — see operations.md if it's taken)
npm run build     # type-check + production bundle to dist/
npm run lint
```

`VITE_API_BASE` overrides the backend URL (default `http://localhost:8000`).
