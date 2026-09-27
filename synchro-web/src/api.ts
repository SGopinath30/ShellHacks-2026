import type { Ledger, LedgerEvent, Opportunity, PairAssessment, Project, QualifiedPairs, ReviewQueue } from './types'

const base = (import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? '' : 'https://gridlock-api-production.up.railway.app'))
  .trim().replace(/\/+$/, '').replace(/\/api\/v1$/, '')

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  const url = `${base}/api/v1${path}`
  const request = () => fetch(url, {
    ...options,
    headers: { ...(options?.body ? { 'Content-Type': 'application/json' } : {}), ...options?.headers },
  })
  try {
    response = await request()
  } catch (firstError) {
    try {
      if (options?.method && options.method.toUpperCase() !== 'GET') throw firstError
      await new Promise(resolve => window.setTimeout(resolve, 500))
      response = await request()
    } catch (lastError) {
      const endpoint = base || window.location.origin
      const detail = lastError instanceof Error ? lastError.message : String(lastError)
      throw new ApiError(0, `Cannot connect to ${endpoint}. Browser error: ${detail}. Check the API URL and this browser's network access.`)
    }
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) detail = body.detail.map((item: { loc?: (string | number)[]; msg?: string }) => `${item.loc?.join('.') ?? 'Input'}: ${item.msg ?? 'Invalid value'}`).join('; ')
    } catch { /* Keep the status message. */ }
    throw new ApiError(response.status, detail)
  }
  return response.json() as Promise<T>
}

export const getProjects = () => api<Project[]>('/projects')
export const getReviewQueue = () => api<ReviewQueue>('/location-review-queue')
export const getQualifiedPairs = () => api<QualifiedPairs>('/qualified-pairs')
export const getAssessment = (a: string, b: string) =>
  api<PairAssessment>(`/pair-assessments?project_a=${encodeURIComponent(a)}&project_b=${encodeURIComponent(b)}`)
export const getOpportunity = (pairId: string) => api<Opportunity>(`/opportunities/${encodeURIComponent(pairId)}`)
const authorized = (key: string): RequestInit => ({ headers: key ? { 'X-API-Key': key } : {} })

export const getLedger = (pairId: string, key: string) => api<Ledger>(`/opportunities/${encodeURIComponent(pairId)}/decision-ledger`, authorized(key))

export type VerificationInput = {
  base_version_id: string
  actor_id: string
  actor_role: string
  reason: string
  location_text: string
  geometry: { type: 'Point'; coordinates: [number, number] }
  geometry_origin: string
  geometry_quality: string
  geometry_evidence: { source_id: string; source_name: string; source_url: string; page_or_row?: string; snippet?: string }
  status?: string
  status_evidence?: { source_id: string; source_name: string; source_url: string; page_or_row?: string; snippet?: string }
}

export const postVerification = (projectId: string, input: VerificationInput, key: string) =>
  api<{ project: Project }>(`/projects/${encodeURIComponent(projectId)}/verify-location`, {
    method: 'POST', body: JSON.stringify(input), ...authorized(key),
  })

export const postDecision = (pairId: string, input: {
  action: string; actor_id: string; actor_role: string; reason: string;
  decision_context_hash: string; idempotency_key: string
}, key: string) => api<LedgerEvent>(`/opportunities/${encodeURIComponent(pairId)}/decisions`, {
  method: 'POST', body: JSON.stringify(input), ...authorized(key),
})
