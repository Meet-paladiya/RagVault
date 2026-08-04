import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { applyTheme, ThemeMode } from '@/theme'

interface ThemeState {
  theme: ThemeMode
  setTheme: (theme: ThemeMode) => void
  toggleTheme: () => void
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'dark',
      setTheme: (theme: ThemeMode) => {
        set({ theme })
        applyTheme(theme)
      },
      toggleTheme: () => {
        const nextTheme: ThemeMode = get().theme === 'dark' ? 'light' : 'dark'
        set({ theme: nextTheme })
        applyTheme(nextTheme)
      },
    }),
    {
      name: 'ragvault-theme-preference',
      onRehydrateStorage: () => (state) => {
        if (state) {
          applyTheme(state.theme)
        } else {
          applyTheme('dark')
        }
      },
    }
  )
)

export function initTheme() {
  const currentTheme = useThemeStore.getState().theme || 'dark'
  applyTheme(currentTheme)
}
