import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from './client'
import type { Document, DocumentListResponse } from '@/types'

export const useDocuments = (chatId?: string, options?: { refetchInterval?: any }) => {
  return useQuery({
    queryKey: ['documents', chatId],
    queryFn: async (): Promise<DocumentListResponse> => {
      const res = await api.get(`/chats/${chatId}/documents`)
      return res.data   // { documents: [...] }
    },
    enabled: !!chatId,
    refetchInterval: options?.refetchInterval ?? ((query: any) => {
      const hasProcessing = query.state.data?.documents?.some(
        (doc: Document) => doc.status === 'processing'
      )
      return hasProcessing ? 3000 : false
    }),
  })
}

export const useUploadDocument = (chatId: string) => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (file: File): Promise<Document> => {
      const formData = new FormData()
      formData.append('file', file)
      const res = await api.post(`/chats/${chatId}/documents`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return res.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents', chatId] })
    },
  })
}

export const useDeleteDocument = (chatId: string) => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (docId: string) => {
      await api.delete(`/chats/${chatId}/documents/${docId}`)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents', chatId] })
    },
  })
}
