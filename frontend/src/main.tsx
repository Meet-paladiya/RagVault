import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { initTheme } from './store/themeStore'
import './index.css'

initTheme()

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Always fetch fresh from server — ensures chat history loads after login/logout
      staleTime: 0,
      // Keep data in cache for 5 minutes while navigating between chats
      gcTime: 5 * 60 * 1000,
      // Re-fetch when user switches back to tab (picks up new messages)
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
