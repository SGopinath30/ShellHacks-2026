import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { resolve } from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";
import { projects } from "./fixtures";
import { safeSourceUrl } from "./utils";
import type { Project } from "./types";

// Render the real TSX component with React's JSX runtime in Node.
const source = readFileSync(resolve(process.cwd(), "components/evidence/SourceEvidence.tsx"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;
const componentModule = { exports: {} as { default?: React.ComponentType<{ projects: Project[] }> } };
const nodeRequire = createRequire(resolve(process.cwd(), "package.json"));
const fixtureRequire = (name: string) =>
  name === "@/lib/utils" ? { safeSourceUrl } : nodeRequire(name);
new Function("require", "module", "exports", compiled)(
  fixtureRequire,
  componentModule,
  componentModule.exports,
);
const SourceEvidence = componentModule.exports.default!;
const render = (input: Project[]) =>
  renderToStaticMarkup(React.createElement(SourceEvidence, { projects: input }));

test("evidence renders duplicate fields, safe links and record-level synthetic labels", () => {
  const example: Project = {
    ...projects[0],
    synthetic: false,
    evidence: [
      {
        field: "Location",
        sourceTitle: "Public map",
        sourceUrl: "https://example.org/map",
        pageOrRow: "Row 4",
        quote: "Point provided",
        synthetic: false,
      },
      {
        field: "Location",
        sourceTitle: "Review note",
        sourceUrl: "javascript:alert(1)",
        pageOrRow: "Page 2",
        quote: "Needs review",
        synthetic: true,
      },
      {
        field: "Schedule",
        sourceTitle: "Internal plan",
        sourceUrl: null,
        pageOrRow: null,
        quote: "Start planned",
        synthetic: false,
      },
    ],
  };
  const html = render([example]);
  assert.equal((html.match(/<details/g) ?? []).length, 3);
  assert.equal((html.match(/<summary>Location/g) ?? []).length, 2);
  assert.match(html, /href="https:\/\/example.org\/map"[^>]*target="_blank"[^>]*rel="noopener noreferrer"/);
  assert.doesNotMatch(html, /href="javascript:/);
  assert.match(html, /Source link unavailable/);
  assert.match(html, /Synthetic evidence/);
  assert.match(html, /Page 2/);
  assert.doesNotMatch(html, /class="section-title"><h3>Source evidence<\/h3><span class="mini-badge">Synthetic/);
  assert.match(render([]), /No source evidence provided/);
  assert.match(render([projects[0]]), /<h3>Source evidence<\/h3><span class="mini-badge">Synthetic/);
});
