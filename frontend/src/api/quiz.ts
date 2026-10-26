import { useQuery, useMutation } from '@tanstack/react-query'
import api from './client'
import { useAuthStore } from '@/store/authStore'
import type {
  Quiz,
  QuizResult,
  RecommendationResponse,
  QuizStreamEvent,
  QuizStreamInitEvent,
  QuizStreamBatchEvent,
  QuizStreamDoneEvent,
} from '@/types'

export interface QuizStreamCallbacks {
  onInit?: (initData: QuizStreamInitEvent) => void
  onBatch: (batchData: QuizStreamBatchEvent) => void
  onDone?: (doneData: QuizStreamDoneEvent) => void
  onError?: (err: Error) => void
}

/**
 * Stream quiz generation in progressive batches via Server-Sent Events (SSE).
 * Delivers first 2-3 MCQs immediately so user doesn't wait, then streams remaining batches.
 */
export const streamQuizGeneration = async (
  chatId: string,
  payload: { topic: string; num_questions: number; initial_batch_size?: number },
  callbacks: QuizStreamCallbacks,
  signal?: AbortSignal
) => {
  try {
    const tokens = useAuthStore.getState().tokens
    const response = await fetch(`/api/chats/${chatId}/quiz/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${tokens?.access_token ?? ''}`,
      },
      body: JSON.stringify({
        topic: payload.topic,
        num_questions: payload.num_questions,
        initial_batch_size: payload.initial_batch_size ?? 3,
      }),
      signal,
    })

    if (!response.ok) {
      let detail = `HTTP ${response.status}: ${response.statusText}`
      try {
        const errorBody = await response.json()
        if (typeof errorBody?.detail === 'string') detail = errorBody.detail
      } catch {
        // Fallback
      }
      throw new Error(detail)
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
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('data:')) continue

        const dataStr = trimmed.replace(/^data:\s*/, '')
        if (dataStr === '[DONE]') {
          return
        }

        try {
          const parsed = JSON.parse(dataStr) as QuizStreamEvent
          if (parsed.type === 'init') {
            callbacks.onInit?.(parsed)
          } else if (parsed.type === 'batch') {
            callbacks.onBatch(parsed)
          } else if (parsed.type === 'done') {
            callbacks.onDone?.(parsed)
          } else if (parsed.type === 'error') {
            callbacks.onError?.(new Error(parsed.detail))
            return
          }
        } catch (e) {
          console.warn('[QUIZ STREAM] Failed to parse SSE message:', dataStr, e)
        }
      }
    }
  } catch (err) {
    if (signal?.aborted) return
    callbacks.onError?.(err instanceof Error ? err : new Error(String(err)))
  }
}

export const useGenerateQuiz = (chatId: string) => {
  return useMutation({
    mutationFn: async (data: { topic: string; num_questions: number }): Promise<Quiz> => {
      const res = await api.post(`/chats/${chatId}/quiz`, data)
      return res.data
    },
  })
}

export const useSubmitQuiz = () => {
  return useMutation({
    mutationFn: async (data: {
      quizId: string
      answers: Record<string, string>
    }): Promise<QuizResult> => {
      const res = await api.post(`/quiz/${data.quizId}/submit`, { answers: data.answers })
      return res.data
    },
  })
}

export const useQuizHistory = (chatId?: string) => {
  return useQuery({
    queryKey: ['quiz-history', chatId],
    queryFn: async (): Promise<Quiz[]> => {
      const res = await api.get(`/chats/${chatId}/quiz-history`)
      return res.data
    },
    enabled: !!chatId,
  })
}

export const useRecommendations = (chatId?: string, options?: { enabled?: boolean }) => {
  return useQuery({
    queryKey: ['recommendations', chatId],
    queryFn: async (): Promise<RecommendationResponse> => {
      const res = await api.get(`/chats/${chatId}/recommendations`)
      return res.data
    },
    enabled: options?.enabled !== undefined ? options.enabled : !!chatId,
  })
}
