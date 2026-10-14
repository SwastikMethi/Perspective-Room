// Query keys and fetchers shared across features.
import { useQuery } from '@tanstack/react-query'
import { api, unwrap } from './client'

export const keys = {
  settings: ['settings'] as const,
  personas: ['personas'] as const,
}

export function useSettings() {
  return useQuery({
    queryKey: keys.settings,
    queryFn: () => unwrap(api.GET('/api/v1/settings')),
    staleTime: 60_000,
  })
}

export function usePersonas() {
  return useQuery({
    queryKey: keys.personas,
    queryFn: () => unwrap(api.GET('/api/v1/personas')),
    staleTime: Infinity,
  })
}
