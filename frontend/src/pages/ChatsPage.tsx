import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { Brain, Plus, Sparkles, RotateCw } from 'lucide-react'
import { useChats, useCreateChat } from '@/api/chats'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/use-toast'
import { useAuthStore } from '@/store/authStore'

export function ChatsPage() {
  const { data, isLoading } = useChats()
  const createChat = useCreateChat()
  const navigate = useNavigate()
  const { toast } = useToast()
  const user = useAuthStore((state) => state.user)
  const [isRedirecting, setIsRedirecting] = useState(false)
  const hasHandledRef = useRef(false)

  const chats = data?.chats ?? []

  useEffect(() => {
    if (isLoading || !user) return

    const storageKey = `ragvault-last-chat:${user.id}`
    const storedChatId = localStorage.getItem(storageKey)
    const storedChat = chats.find((chat) => chat.id === storedChatId)
    const targetChat = storedChat ?? chats[0]

    if (!targetChat) {
      if (hasHandledRef.current) return
      hasHandledRef.current = true
      setIsRedirecting(true)
      createChat.mutateAsync({ title: 'New Chat' })
        .then((chat) => {
          localStorage.setItem(storageKey, chat.id)
          navigate(`/chats/${chat.id}`, { replace: true })
        })
        .catch(() => {
          setIsRedirecting(false)
          hasHandledRef.current = false
          toast({ title: 'Error', description: "Failed to create initial chat.", variant: 'destructive' })
        })
      return
    }

    if (hasHandledRef.current) return

    hasHandledRef.current = true
    setIsRedirecting(true)
    localStorage.setItem(storageKey, targetChat.id)
    navigate(`/chats/${targetChat.id}`, { replace: true })
  }, [isLoading, user, chats, createChat, navigate, toast])

  const handleCreate = async () => {
    try {
      const chat = await createChat.mutateAsync({ title: 'New Chat' })
      navigate(`/chats/${chat.id}`)
    } catch {
      toast({ title: 'Error', description: 'Failed to create chat.', variant: 'destructive' })
    }
  }

  if (isLoading || isRedirecting || createChat.isPending) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-primary/20 to-blue-600/20 border border-primary/30 flex items-center justify-center animate-glow">
          <RotateCw className="w-6 h-6 text-primary animate-spin" />
        </div>
        <p className="text-xs font-medium text-muted-foreground">Opening Knowledge Space...</p>
      </div>
    )
  }

  return (
    <div className="h-full flex items-center justify-center">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="text-center max-w-md px-6"
      >
        <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-primary/20 to-blue-600/20 border border-primary/30 flex items-center justify-center mx-auto mb-6 animate-glow">
          <Brain className="w-10 h-10 text-primary" />
        </div>
        <h1 className="text-3xl font-bold gradient-text mb-3">Welcome to RagVault</h1>
        <p className="text-muted-foreground mb-8 text-sm leading-relaxed">
          Create your first knowledge space. Upload your study materials — PDFs, slides, lectures — and
          start chatting with your documents powered by local AI.
        </p>
        <div className="flex flex-col items-center gap-3">
          <Button
            onClick={handleCreate}
            className="btn-gradient text-white border-0 px-8 py-6 text-base rounded-xl"
            disabled={createChat.isPending}
          >
            <Plus className="w-5 h-5 mr-2" />
            {createChat.isPending ? 'Creating…' : 'Create Knowledge Space'}
          </Button>
          <div className="flex items-center gap-2 text-xs text-muted-foreground mt-2">
            <Sparkles className="w-3.5 h-3.5 text-primary" />
            100% offline · no data leaves your device
          </div>
        </div>
      </motion.div>
    </div>
  )
}
