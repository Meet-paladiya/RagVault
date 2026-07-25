import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { Brain, Plus, Sparkles } from 'lucide-react'
import { useChats, useCreateChat } from '@/api/chats'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/use-toast'
import { useEffect } from 'react'

export function ChatsPage() {
  const { data, isLoading } = useChats()
  const createChat = useCreateChat()
  const navigate = useNavigate()
  const { toast } = useToast()

  const chats = data?.chats ?? []

  // Auto-redirect to most recent chat if any
  useEffect(() => {
    if (!isLoading && chats.length > 0) {
      navigate(`/chats/${chats[0].id}`, { replace: true })
    }
  }, [isLoading, chats, navigate])

  const handleCreate = async () => {
    try {
      const chat = await createChat.mutateAsync({ title: 'New Knowledge Space' })
      navigate(`/chats/${chat.id}`)
    } catch {
      toast({ title: 'Error', description: 'Failed to create chat.', variant: 'destructive' })
    }
  }

  if (isLoading) return null

  return (
    <div className="h-full flex items-center justify-center">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="text-center max-w-md px-6"
      >
        <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-purple-500/20 to-indigo-600/20 border border-purple-500/30 flex items-center justify-center mx-auto mb-6 animate-glow">
          <Brain className="w-10 h-10 text-purple-400" />
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
            <Sparkles className="w-3.5 h-3.5 text-purple-400" />
            100% offline · no data leaves your device
          </div>
        </div>
      </motion.div>
    </div>
  )
}
