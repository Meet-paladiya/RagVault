import { useQuery, useMutation } from '@tanstack/react-query'
import api from './client'
import type { Quiz, QuizResult, RecommendationResponse } from '@/types'

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
