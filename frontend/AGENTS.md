# UrjaSetu frontend — mandatory team and AI instructions

Read this file and FRONTEND_GUIDE.md before editing. The user's frontend-only scope overrides old phase assignments.

1. **Never modify backend/**, data/, scripts/, evaluation/, migrations, Python dependencies, Docker, root environment files or backend CI. Backend files are read-only references. Report missing APIs; never create or change them.
2. Work only in frontend/ unless the user explicitly assigns another documentation file. Do not commit, merge, push, reset, stash or discard another contributor's work. Inspect git status before and after. Use a feature branch; coordinate shared files with Yagnik.
3. Four humans share this project. Unexpected modifications belong to teammates. Preserve them. Do not spawn parallel AI agents without an explicit request.
4. React + TypeScript + Vite; TanStack Query for server state; Recharts for charts; Motion for transitions; React Flow for topology; Lucide for icons. Lock dependencies. Add libraries only for an actual feature. No duplicate state stores or component libraries.
5. Pages live in src/features/<feature>/. Reuse src/components/ for cards, badges, tables, charts, dialogs and forms. Tokens live in src/styles/tokens.css. Network calls live in src/lib/api.ts. Do not copy business logic into the browser.
6. Treat mounted backend routers and Pydantic schemas as implementation truth; documentation includes unimplemented endpoints. Never invent URLs, response properties or successful writes.
7. Demo values must be visibly identified as illustrative. Never silently substitute demo data after API failure. Do not call synthetic charts live. Never approve trades, determine grid safety, calculate authoritative prices or settle money in frontend state.
8. REST is authoritative. WebSocket notifications invalidate/refetch REST queries, including on ready/reconnect. WebSocket uses /ws/{market|grid|telemetry}?user_id=UUID; protected REST uses X-User-Id. These are prototype identities, not production authentication.
9. Preserve null measurements as unavailable, never zero. Power kW; energy kWh; voltage pu; price INR/kWh. Keep decimal strings in transport; convert only for display. Send ISO UTC, display Asia/Kolkata with timezone labels.
10. Market is day-ahead. Proposed trades are not committed. Unknown/failed grid validation is not safe. Settlement is simulated accounting, not a withdrawable wallet. Physical electricity travels through the DISCOM grid, not peer-to-peer routes.
11. Every action needs feedback, validation and disabled/loading/error states. Support keyboard navigation, visible focus, labeled inputs, accessible dialogs, reduced motion and narrow screens. Never use color alone for status.
12. Store replacement image assets in public/images/placeholders/ and document their intended use. No secrets, personal account numbers, remote tracking or production credentials in browser bundles.
13. Run npm run check, npm run build and npm test; inspect desktop and mobile. Handoff changed paths, checks, limitations and API gaps. Do not run backend migrations/seeds/tests as part of frontend work.
