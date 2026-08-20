import { useQuery } from '@tanstack/react-query'
import api from './client'
import { useAuthStore } from '@/store/authStore'
import type { MessageListResponse } from '@/types'

export const useMessages = (chatId?: string) => {
  return useQuery({
    queryKey: ['messages', chatId],
    queryFn: async (): Promise<MessageListResponse> => {
      const res = await api.get(`/chats/${chatId}/messages`)
      return res.data   // { messages: [...] }
    },
    enabled: !!chatId,
  })
}

/**
 * Stream a RAG response via SSE.
 * The backend returns:
 *   data: {"token": "..."}      → partial answer token (JSON encoded)
 *   data: {"citations": [...]}  → citation metadata
 *   data: [DONE]               → stream complete
 *
 * The backend POST endpoint is /chats/{chatId}/messages with stream=true.
 */
export const streamMessage = async (
  chatId: string,
  content: string,
  onToken: (text: string) => void,
  onDone: () => void,
  onError: (err: unknown) => void,
  signal?: AbortSignal,
) => {
  try {
    const tokens = useAuthStore.getState().tokens
    const response = await fetch(`/api/chats/${chatId}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${tokens?.access_token ?? ''}`,
      },
      body: JSON.stringify({ content, stream: true }),
      signal,
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }

    const reader = response.body?.getReader()
    const decoder = new TextDecoder()
    if (!reader) throw new Error('No stream reader available')

    let buffer = ''

    while (true) {
      if (signal?.aborted) {
        await reader.cancel()
        return
      }

      const { value, done } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // Process complete SSE lines
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''   // keep incomplete last line in buffer

      for (const line of lines) {
        if (signal?.aborted) {
          await reader.cancel()
          return
        }

        const trimmed = line.trim()
        if (!trimmed.startsWith('data: ')) continue
        const raw = trimmed.slice(6).trim()

        if (raw === '[DONE]') {
          await reader.cancel()
          onDone()
          return
        }

        // Try parsing JSON payload ({"token": "..."})
        try {
          const parsed = JSON.parse(raw)
          if (typeof parsed === 'object' && parsed !== null) {
            if ('token' in parsed && typeof parsed.token === 'string') {
              onToken(parsed.token)
              continue
            }
            if ('citations' in parsed) {
              // Citations metadata event
              continue
            }
          }
        } catch {
          // Fallback for plain text stream chunks
          if (raw && !raw.startsWith('__citations__:')) {
            onToken(raw)
          }
        }
      }
    }

    if (!signal?.aborted) {
      onDone()
    }
  } catch (error) {
    if ((error as { name?: string })?.name === 'AbortError') {
      return
    }
    onError(error)
  }
}
