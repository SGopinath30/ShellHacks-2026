# SYNCHRO web

Original React frontend for the SYNCHRO planning workflow. It uses [Motion for React](https://motion.dev/docs/react) (the current Framer Motion package) for page, card, and panel animation. It does not use Page UI.

The landing hero includes [React Bits AeroShards](https://reactbits.dev/c/backgrounds/aero-shards) (JavaScript + CSS) with `vgpu`, styled in SYNCHRO teal. It loads only on the landing page, pauses for reduced-motion preferences, and leaves the normal hero background in place if WebGPU setup fails. Source: [React Bits repository](https://github.com/DavidHDev/react-bits/tree/main/src/content/Backgrounds/AeroShards).

## Run

From `synchro-web/`:

Use Node.js 20.19+ or 22.12+.

```bash
npm install
npm run dev
```

Open the Vite URL. In development, the browser calls Vite on the same origin and Vite proxies `/api` and `/health` to the team's Railway API. Set `VITE_DEV_API_TARGET=http://127.0.0.1:8000` to proxy to a local `gridlock-control-plane` server instead. A nonempty `VITE_API_BASE_URL` makes the browser call that origin directly. Production builds default to the Railway API.

If the page reports a connection error, check the API address shown in the message and open `https://gridlock-api-production.up.railway.app/health` from the same browser. A deployment-specific `VITE_API_BASE_URL` overrides the default at build time; set it to the API origin (with `https://`) and rebuild. Public GET requests do not send a JSON content header, avoiding an unnecessary browser preflight.

The application never substitutes preview records into live screens. If the project endpoint works but the review routes are missing, it shows the real project versions and a deployment mismatch notice; qualification and writes remain unavailable. With the current backend connected, the Location Workbench, pair comparison, qualified opportunities, evidence, and Decision Ledger use the live `/api/v1` endpoints. Example records live only in `scripts/render-fixtures.ts` for the render smoke test.

`WRITE_API_KEY` remains configured on the backend and is never built into the frontend. An authorized reviewer can enter it through **Reviewer access** for protected location verification, Decision Ledger reads, and manager decisions. The key lives only in React memory for the current tab and is sent in `X-API-Key` over HTTPS. Use this on a trusted device; a shared key does not establish individual identity. The API currently accepts client-asserted actor IDs.

```bash
npm run build
npm run check:render
npm run preview
```

## AI research and human approval

The Location Workbench can start Gemini research after Reviewer access is set.
Review retrieved sources, missing evidence, proposed coordinates/status, and any
outreach draft. Edit and save the proposal if needed, then explicitly confirm
the evidence and approve or reject. Research alone never changes a project.
Backend configuration and limitations: [AI_RESEARCH.md](../gridlock-control-plane/AI_RESEARCH.md).
