import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { AppShell } from '@/components/layout/AppShell'
import { LoginPage } from '@/pages/LoginPage'
import { RegisterPage } from '@/pages/RegisterPage'
import { ChatsPage } from '@/pages/ChatsPage'
import { ChatDetailPage } from '@/pages/ChatDetailPage'
import { QuizPage } from '@/pages/QuizPage'
import { Toaster } from '@/components/ui/toaster'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const tokens = useAuthStore((s) => s.tokens)
  if (!tokens?.access_token) return <Navigate to="/login" replace />
  return <>{children}</>
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const tokens = useAuthStore((s) => s.tokens)
  if (tokens?.access_token) return <Navigate to="/chats" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/chats" replace />} />
        <Route
          path="/login"
          element={<PublicRoute><LoginPage /></PublicRoute>}
        />
        <Route
          path="/register"
          element={<PublicRoute><RegisterPage /></PublicRoute>}
        />
        <Route
          path="/chats"
          element={
            <ProtectedRoute>
              <AppShell>
                <ChatsPage />
              </AppShell>
            </ProtectedRoute>
          }
        />
        <Route
          path="/chats/:chatId"
          element={
            <ProtectedRoute>
              <AppShell>
                <ChatDetailPage />
              </AppShell>
            </ProtectedRoute>
          }
        />
        <Route
          path="/quiz"
          element={
            <ProtectedRoute>
              <AppShell>
                <QuizPage />
              </AppShell>
            </ProtectedRoute>
          }
        />
      </Routes>
      <Toaster />
    </BrowserRouter>
  )
}
