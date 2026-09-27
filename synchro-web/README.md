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

Open the Vite URL. By default, reads use the team's deployed Railway API. Set `VITE_API_BASE_URL=http://127.0.0.1:8000` to use a local `gridlock-control-plane` server. The dev server also proxies `/api` to that local service when the base URL is empty.

The application never substitutes preview records into live screens. If the project endpoint works but the review routes are missing, it shows the real project versions and a deployment mismatch notice; qualification and writes remain unavailable. With the current backend connected, the Location Workbench, pair comparison, qualified opportunities, evidence, and Decision Ledger use the live `/api/v1` endpoints. Example records live only in `scripts/render-fixtures.ts` for the render smoke test.

`WRITE_API_KEY` remains configured on the backend and is never built into the frontend. An authorized reviewer can enter it through **Reviewer access** for protected location verification, Decision Ledger reads, and manager decisions. The key lives only in React memory for the current tab and is sent in `X-API-Key` over HTTPS. Use this on a trusted device; a shared key does not establish individual identity. The API currently accepts client-asserted actor IDs.

```bash
npm run build
npm run check:render
npm run preview
```
