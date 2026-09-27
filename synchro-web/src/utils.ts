export function safeSourceUrl(value: string | null | undefined): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}

export function formatMiles(meters: number, digits = 2): string {
  return (meters / 1609.344).toFixed(digits)
}
