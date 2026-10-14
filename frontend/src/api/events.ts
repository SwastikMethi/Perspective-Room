// Run event payloads (G2). RunEvent.data is free-form in the contract, so its shapes live here.
import type { Schemas } from './client'

export const TERMINAL_EVENTS = [
  'run.completed',
  'run.partial',
  'run.cancelled',
  'run.failed',
  'run.interrupted',
] as const

export const EVENT_TYPES = [
  'run.queued',
  'run.started',
  'run.stage',
  'research.completed',
  'message.completed',
  'run.warning',
  ...TERMINAL_EVENTS,
] as const

export type RunEventType = (typeof EVENT_TYPES)[number]
export type TerminalEventType = (typeof TERMINAL_EVENTS)[number]

export interface QueuedData {
  status: Schemas['Run']['status']
  stage: string
  session_version: number
  audience: Schemas['TurnControl']['audience']
  slots: string[]
}
export interface StageData {
  stage: string
  persona_id: string | null
  status_key: string
}
export interface ResearchData {
  research_pack_id: string
  source_ids: string[]
  availability: 'available' | 'empty' | 'failed'
}
export interface MessageData {
  message: Schemas['Message']
  session_version: number
}
export interface WarningData {
  code: string
  text: string
  degraded: boolean
}
export interface TerminalData {
  run: Schemas['Run']
  missing_persona_ids: string[]
}

export type RunEventEnvelope =
  | {
      id: string
      run_id: string
      created_at: string
      type: 'run.queued' | 'run.started'
      data: QueuedData
    }
  | { id: string; run_id: string; created_at: string; type: 'run.stage'; data: StageData }
  | {
      id: string
      run_id: string
      created_at: string
      type: 'research.completed'
      data: ResearchData
    }
  | { id: string; run_id: string; created_at: string; type: 'message.completed'; data: MessageData }
  | { id: string; run_id: string; created_at: string; type: 'run.warning'; data: WarningData }
  | { id: string; run_id: string; created_at: string; type: TerminalEventType; data: TerminalData }

export function isTerminal(type: string): type is TerminalEventType {
  return (TERMINAL_EVENTS as readonly string[]).includes(type)
}
