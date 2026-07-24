import axios from 'axios'
import { useAuthStore } from '@/store/authStore'

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor: attach Bearer token
api.interceptors.request.use((config) => {
  const tokens = useAuthStore.getState().tokens
  if (tokens?.access_token) {
    config.headers.Authorization = `Bearer ${tokens.access_token}`
  }
  return config
})

// Response interceptor: auto-refresh on 401
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const originalRequest = error.config
    // If 401 and not already retrying
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true
      try {
        const tokens = useAuthStore.getState().tokens
        if (!tokens?.refresh_token) {
          throw new Error('No refresh token')
        }
        
        // Call refresh endpoint directly with axios to avoid loop
        const res = await axios.post('/api/auth/refresh', {
          refresh_token: tokens.refresh_token,
        })
        
        const newTokens = res.data
        useAuthStore.getState().updateTokens(newTokens)
        
        originalRequest.headers.Authorization = `Bearer ${newTokens.access_token}`
        return axios(originalRequest)
      } catch (err) {
        useAuthStore.getState().clearAuth()
        window.location.href = '/login'
        return Promise.reject(err)
      }
    }
    return Promise.reject(error)
  }
)

export default api
