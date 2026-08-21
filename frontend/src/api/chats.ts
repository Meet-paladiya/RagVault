import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from './client'
import type { Chat, ChatListResponse } from '@/types'

export const useChats = () => {
  return useQuery({
    queryKey: ['chats'],
    queryFn: async (): Promise<ChatListResponse> => {
      const res = await api.get('/chats')
      return res.data   // backend returns { chats: [...] }
    },
  })
}

export const useChat = (chatId?: string) => {
  return useQuery({
    queryKey: ['chat', chatId],
    queryFn: async (): Promise<Chat> => {
      const res = await api.get(`/chats/${chatId}`)
      return res.data
    },
    enabled: !!chatId,
  })
}

export const useCreateChat = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (data: { title: string }): Promise<Chat> => {
      const res = await api.post('/chats', data)
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chats'] })
    },
  })
}

export const useDeleteChat = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (chatId: string) => {
      await api.delete(`/chats/${chatId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chats'] })
    },
  })
}

export const useClearKnowledge = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (chatId: string) => {
      const res = await api.delete(`/chats/${chatId}/clear-knowledge`)
      return res.data
    },
    onSuccess: (_, chatId) => {
      queryClient.invalidateQueries({ queryKey: ['documents', chatId] })
      queryClient.invalidateQueries({ queryKey: ['messages', chatId] })
    },
  })
}
