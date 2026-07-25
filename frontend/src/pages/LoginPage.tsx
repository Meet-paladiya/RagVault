import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Mail, Lock, Brain, Sparkles } from 'lucide-react'
import { useLoginMutation } from '@/api/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/components/ui/use-toast'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()
  const login = useLoginMutation()
  const { toast } = useToast()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      await login.mutateAsync({ email, password })
      navigate('/chats')
    } catch {
      toast({ title: 'Login failed', description: 'Invalid email or password.', variant: 'destructive' })
    }
  }

  return (
    <div className="min-h-screen flex bg-background">
      {/* Left — animated hero */}
      <div className="hidden lg:flex flex-1 items-center justify-center relative overflow-hidden bg-gradient-to-br from-purple-900/40 via-background to-indigo-900/30">
        <div className="absolute inset-0">
          <div className="absolute top-1/4 left-1/4 w-64 h-64 bg-purple-600/20 rounded-full blur-3xl animate-pulse" />
          <div className="absolute bottom-1/3 right-1/4 w-48 h-48 bg-indigo-600/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
        </div>
        <div className="relative z-10 text-center px-8">
          <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center mx-auto mb-6 animate-glow">
            <Brain className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-4xl font-bold gradient-text mb-3">RagVault</h1>
          <p className="text-muted-foreground text-lg max-w-xs">
            Your offline AI-powered study companion. Chat with your documents. Learn smarter.
          </p>
          <div className="mt-8 flex flex-col gap-3 text-sm text-muted-foreground">
            {['100% offline — no internet required', 'PDF, PPTX, Video, Audio support', 'AI quizzes & personalised study plans'].map((f) => (
              <div key={f} className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-purple-400" />
                <span>{f}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right — login form */}
      <div className="flex-1 flex items-center justify-center px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-sm"
        >
          <div className="glass-card rounded-2xl p-8">
            <div className="mb-8">
              <h2 className="text-2xl font-bold text-foreground">Welcome back</h2>
              <p className="text-sm text-muted-foreground mt-1">Sign in to your knowledge space</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="space-y-1.5">
                <Label htmlFor="email" className="text-xs">Email</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    required
                    className="pl-10 bg-white/5 border-white/10"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="password" className="text-xs">Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    className="pl-10 bg-white/5 border-white/10"
                  />
                </div>
              </div>

              <Button
                type="submit"
                className="w-full btn-gradient text-white border-0 h-11"
                disabled={login.isPending}
              >
                {login.isPending ? 'Signing in…' : 'Sign In'}
              </Button>
            </form>

            <p className="text-xs text-muted-foreground text-center mt-6">
              Don't have an account?{' '}
              <Link to="/register" className="text-purple-400 hover:text-purple-300 font-medium">
                Register
              </Link>
            </p>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
