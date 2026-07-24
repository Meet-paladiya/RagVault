import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User, AuthTokens } from '@/types'

interface AuthState {
  user: User | null
  tokens: AuthTokens | null
  setAuth: (user: User, tokens: AuthTokens) => void
  clearAuth: () => void
  updateTokens: (tokens: AuthTokens) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      tokens: null,
      setAuth: (user, tokens) => set({ user, tokens }),
      clearAuth: () => set({ user: null, tokens: null }),
      updateTokens: (tokens) => set({ tokens }),
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({ tokens: state.tokens, user: state.user }),
    }
  )
)
