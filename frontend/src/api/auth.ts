import { useMutation } from '@tanstack/react-query'
import api from './client'
import { useAuthStore } from '@/store/authStore'

export const useRegisterMutation = () => {
  const setAuth = useAuthStore((s) => s.setAuth)
  return useMutation({
    mutationFn: async (data: { name: string; email: string; password: string }) => {
      const res = await api.post('/auth/register', data)
      return res.data
    },
    onSuccess: (data) => {
      // data has: { user: {...}, access_token, refresh_token, token_type }
      setAuth(data.user, {
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        token_type: data.token_type,
      })
    },
  })
}

export const useLoginMutation = () => {
  const setAuth = useAuthStore((s) => s.setAuth)
  return useMutation({
    mutationFn: async (data: { email: string; password: string }) => {
      const res = await api.post('/auth/login', data)
      return res.data
    },
    onSuccess: (data) => {
      // data has: { access_token, refresh_token, token_type }
      // Fetch user info after login
      api.get('/auth/me').then((res) => {
        setAuth(res.data, {
          access_token: data.access_token,
          refresh_token: data.refresh_token,
          token_type: data.token_type,
        })
      })
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
