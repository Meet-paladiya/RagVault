import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'
import api from './client'
import type { NotesResponse } from '@/types'

export const useNotes = (chatId?: string) => {
  return useQuery({
    queryKey: ['notes', chatId],
    queryFn: async (): Promise<NotesResponse | null> => {
      try {
        const res = await api.get(`/chats/${chatId}/notes`)
        return res.data
      } catch (error) {
        if (axios.isAxiosError(error) && error.response?.status === 404) {
          return null
        }
        throw error
      }
    },
    enabled: !!chatId,
    retry: false,
  })
}

export const useGenerateNotes = (chatId: string) => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (): Promise<NotesResponse> => {
      const res = await api.post(`/chats/${chatId}/notes`)
      return res.data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['notes', chatId], data)
    },
  })
}
