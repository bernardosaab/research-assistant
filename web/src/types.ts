export interface Source {
  id: number
  url: string
  title: string
}

export interface Brief {
  topic: string
  markdown: string
  sources: Source[]
}

export interface RunTrace {
  variant: string
  topic: string
  duration_seconds: number
  llm_calls: number
  search_calls: number
  input_tokens: number
  output_tokens: number
}

export type RunStatus = 'running' | 'done' | 'error'

export interface RunRecord {
  run_id: string
  status: RunStatus
  topic: string
  variant: string
  created_at: string
  brief: Brief | null
  trace: RunTrace | null
  error: string | null
}
