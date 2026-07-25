import { useMutation } from '@tanstack/react-query'
import api from './client'
import { useAuthStore } from '@/store/authStore'

export const useRegisterMutation = () => {
  const setAuth = useAuthStore((s) => s.setAuth)
  return useMutation({
    mutationFn: async (data: { name: string; email: string; password: string }) => {
      const res = await api.post('/auth/register', data)
      const dataObj = res.data
      setAuth(dataObj.user, {
        access_token: dataObj.access_token,
        refresh_token: dataObj.refresh_token,
        token_type: dataObj.token_type,
      })
      return dataObj
    },
  })
}

export const useLoginMutation = () => {
  const setAuth = useAuthStore((s) => s.setAuth)
  return useMutation({
    mutationFn: async (data: { email: string; password: string }) => {
      const loginRes = await api.post('/auth/login', data)
      const tokens = loginRes.data
      
      const meRes = await api.get('/auth/me', {
        headers: {
          Authorization: `Bearer ${tokens.access_token}`,
        },
      })
      
      const user = meRes.data
      setAuth(user, tokens)
      return { user, tokens }
    },
  })
}

export const useLogout = () => {
  const clearAuth = useAuthStore((s) => s.clearAuth)
  return () => {
    clearAuth()
    window.location.href = '/login'
  }
}
