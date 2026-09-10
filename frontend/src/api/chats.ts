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
    // Always load from DB — never serve stale empty list after login
    refetchOnMount: 'always',
    staleTime: 0,
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
    refetchOnMount: 'always',
    staleTime: 0,
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
    mutationFn: async (payload: string | { chatId: string; purge?: boolean }) => {
      const chatId = typeof payload === 'string' ? payload : payload.chatId
      const doPurge = typeof payload === 'string' || payload.purge !== false
      const url = `/chats/${chatId}${doPurge ? '?purge=true' : ''}`
      await api.delete(url)
    },
    onSuccess: (_, payload) => {
      const chatId = typeof payload === 'string' ? payload : payload.chatId
      queryClient.invalidateQueries({ queryKey: ['chats'] })
      if (chatId) {
        queryClient.removeQueries({ queryKey: ['chat', chatId] })
        queryClient.removeQueries({ queryKey: ['messages', chatId] })
        queryClient.removeQueries({ queryKey: ['documents', chatId] })
        queryClient.removeQueries({ queryKey: ['notes', chatId] })
        queryClient.removeQueries({ queryKey: ['remedial-notes', chatId] })
      }
    },
  })
}

export const useUpdateChat = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (data: { chatId: string; title: string }): Promise<Chat> => {
      const res = await api.patch(`/chats/${data.chatId}`, { title: data.title })
      return res.data
    },
    onSuccess: (chat) => {
      queryClient.setQueryData(['chat', chat.id], chat)
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
