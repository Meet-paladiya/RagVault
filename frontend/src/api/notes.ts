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

export const downloadNotesPdf = async (chatId: string): Promise<void> => {
  const res = await api.get(`/chats/${chatId}/notes/pdf`, { responseType: 'blob' })
  const url = URL.createObjectURL(res.data)
  const link = document.createElement('a')
  link.href = url
  link.download = `ragvault-notes-${chatId}.pdf`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export const useRemedialNotes = (chatId?: string) => {
  return useQuery({
    queryKey: ['remedialNotes', chatId],
    queryFn: async (): Promise<NotesResponse | null> => {
      try {
        const res = await api.get(`/chats/${chatId}/quiz-remedial-notes`)
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

export const useGenerateRemedialNotes = (chatId: string) => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (quizId?: string): Promise<NotesResponse> => {
      const url = quizId ? `/chats/${chatId}/quiz-remedial-notes?quiz_id=${quizId}` : `/chats/${chatId}/quiz-remedial-notes`
      const res = await api.post(url)
      return res.data
    },
    onSuccess: (data) => {
      queryClient.setQueryData(['remedialNotes', chatId], data)
    },
  })
}

export const downloadRemedialNotesPdf = async (chatId: string): Promise<void> => {
  const res = await api.get(`/chats/${chatId}/quiz-remedial-notes/pdf`, { responseType: 'blob' })
  const url = URL.createObjectURL(res.data)
  const link = document.createElement('a')
  link.href = url
  link.download = `ragvault-quiz-remedial-${chatId}.pdf`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
