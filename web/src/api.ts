import type { RunRecord } from './types'

const BASE = '/api'

export async function getVariants(): Promise<string[]> {
  const response = await fetch(`${BASE}/variants`)
  if (!response.ok) {
    throw new Error(`Failed to load variants: ${response.status}`)
  }
  return response.json()
}

export async function createRun(topic: string, variant: string): Promise<string> {
  const response = await fetch(`${BASE}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, variant }),
  })
  if (!response.ok) {
    throw new Error(`Failed to create run: ${response.status}`)
  }
  const data = await response.json()
  return data.run_id
}

export async function getRun(runId: string): Promise<RunRecord> {
  const response = await fetch(`${BASE}/runs/${runId}`)
  if (!response.ok) {
    throw new Error(`Failed to fetch run: ${response.status}`)
  }
  return response.json()
}

export async function getRuns(): Promise<RunRecord[]> {
  const response = await fetch(`${BASE}/runs`)
  if (!response.ok) {
    throw new Error(`Failed to fetch runs: ${response.status}`)
  }
  return response.json()
}
