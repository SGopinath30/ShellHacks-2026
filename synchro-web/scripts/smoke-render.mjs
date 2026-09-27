import assert from 'node:assert/strict'
import React from 'react'
import { renderToString } from 'react-dom/server'
import { createServer } from 'vite'

const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom' })
try {
  const [{ default: Landing }, { default: Workbench }, { default: Opportunities }, demo] = await Promise.all([
    vite.ssrLoadModule('/src/Landing.tsx'),
    vite.ssrLoadModule('/src/Workbench.tsx'),
    vite.ssrLoadModule('/src/Opportunities.tsx'),
    vite.ssrLoadModule('/scripts/render-fixtures.ts'),
  ])
  const landing = renderToString(React.createElement(Landing, {
    projects: demo.previewProjects, queue: demo.previewQueue,
    pairs: { maximum_meters: 40000, total: 0, opportunities: [] }, live: true, loading: false,
  }))
  const workbench = renderToString(React.createElement(Workbench, {
    projects: demo.previewProjects, queue: demo.previewQueue, maximumMeters: 40000, live: true,
    projectsLoaded: true, apiError: '', loading: false, onReload: async () => {}, accessKey: '',
  }))
  const opportunities = renderToString(React.createElement(Opportunities, {
    data: { maximum_meters: 40000, total: 0, opportunities: [] }, live: true, apiError: '', accessKey: '',
  }))
  const unavailable = renderToString(React.createElement(Opportunities, {
    data: { maximum_meters: 40000, total: 0, opportunities: [] }, live: false,
    apiError: 'The deployed API is missing qualified-pairs.', accessKey: '',
  }))
  assert.match(landing, /Every utility sees its plan/)
  assert.match(workbench, /Location Workbench/)
  assert.match(workbench, /Winnsboro West/)
  assert.match(opportunities, /No current DESC/)
  assert.match(unavailable, /Opportunity analysis unavailable/)
  assert.doesNotMatch(unavailable, /NO QUALIFIED PAIR YET/)
  console.log('Landing, workbench, and empty opportunity views render successfully.')
} finally {
  await vite.close()
}
