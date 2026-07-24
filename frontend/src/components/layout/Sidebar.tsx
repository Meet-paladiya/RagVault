import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Brain, MessageSquare, Plus, Search, LogOut, ChevronLeft,
  BookOpen, History, Zap,
} from 'lucide-react'
import { useChats, useCreateChat, useDeleteChat } from '@/api/chats'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useToast } from '@/components/ui/use-toast'
import { formatDistanceToNow } from 'date-fns'

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { chatId } = useParams()
  const navigate = useNavigate()
  const { user, clearAuth } = useAuthStore()
  const { data: chatsData } = useChats()
  const createChat = useCreateChat()
  const deleteChat = useDeleteChat()
  const { toast } = useToast()
  const [search, setSearch] = useState('')
  const [creating, setCreating] = useState(false)
  const [newTitle, setNewTitle] = useState('')

  const chats = chatsData?.chats ?? []
  const filtered = chats.filter((c) =>
    c.title.toLowerCase().includes(search.toLowerCase())
  )

  const handleCreateChat = async () => {
    if (!newTitle.trim()) return
    try {
      const chat = await createChat.mutateAsync({ title: newTitle.trim() })
      setNewTitle('')
      setCreating(false)
      navigate(`/chats/${chat.id}`)
    } catch {
      toast({ title: 'Error', description: 'Failed to create chat.', variant: 'destructive' })
    }
  }

  const handleLogout = () => {
    clearAuth()
    navigate('/login')
  }

  return (
    <motion.div
      animate={{ width: collapsed ? 64 : 280 }}
      transition={{ duration: 0.3, ease: 'easeInOut' }}
      className="relative flex flex-col h-full glass border-r border-white/10 overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-5 border-b border-white/10">
        <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-gradient-to-br from-purple-500 to-indigo-600 flex items-center justify-center">
          <Brain className="w-4 h-4 text-white" />
        </div>
        {!collapsed && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="font-semibold text-sm gradient-text whitespace-nowrap"
          >
            Knowledge Hub
          </motion.span>
        )}
        <button
          onClick={onToggle}
          className="ml-auto text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className={`w-4 h-4 transition-transform duration-300 ${collapsed ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {!collapsed && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="px-3 py-3">
          {/* Search */}
          <div className="relative mb-3">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search chats..."
              className="pl-8 h-8 text-xs bg-white/5 border-white/10"
            />
          </div>

          {/* New Chat Button */}
          {creating ? (
            <div className="flex gap-1.5 mb-3">
              <Input
                autoFocus
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleCreateChat(); if (e.key === 'Escape') setCreating(false) }}
                placeholder="Chat title..."
                className="h-8 text-xs bg-white/5 border-white/10 flex-1"
              />
              <Button size="sm" className="h-8 btn-gradient text-white border-0" onClick={handleCreateChat}>
                Add
              </Button>
            </div>
          ) : (
            <Button
              onClick={() => setCreating(true)}
              className="w-full h-8 text-xs btn-gradient text-white border-0 mb-3"
              size="sm"
            >
              <Plus className="w-3.5 h-3.5 mr-1.5" />
              New Chat
            </Button>
          )}
        </motion.div>
      )}

      {/* Chat List */}
      <ScrollArea className="flex-1 px-2">
        <div className="space-y-0.5 pb-2">
          {filtered.map((chat) => (
            <Link key={chat.id} to={`/chats/${chat.id}`}>
              <motion.div
                whileHover={{ x: 2 }}
                className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg cursor-pointer group transition-all duration-150 ${
                  chatId === chat.id
                    ? 'bg-primary/15 border-l-2 border-primary text-foreground'
                    : 'hover:bg-white/5 text-muted-foreground hover:text-foreground'
                }`}
              >
                <MessageSquare className="w-3.5 h-3.5 flex-shrink-0" />
                {!collapsed && (
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{chat.title}</p>
                    <p className="text-[10px] text-muted-foreground">
                      {formatDistanceToNow(new Date(chat.updated_at), { addSuffix: true })}
                    </p>
                  </div>
                )}
              </motion.div>
            </Link>
          ))}
          {!collapsed && filtered.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-4">
              {search ? 'No matches' : 'No chats yet'}
            </p>
          )}
        </div>
      </ScrollArea>

      {/* Bottom Nav */}
      {!collapsed && (
        <div className="border-t border-white/10 px-3 py-3 space-y-1">
          <Link to="/quiz">
            <Button variant="ghost" size="sm" className="w-full justify-start text-xs h-8">
              <History className="w-3.5 h-3.5 mr-2" /> Quiz History
            </Button>
          </Link>
        </div>
      )}

      {/* User Row */}
      <div className={`border-t border-white/10 p-3 flex items-center gap-2 ${collapsed ? 'justify-center' : ''}`}>
        <Avatar className="w-7 h-7 flex-shrink-0">
          <AvatarFallback className="bg-primary/20 text-primary text-xs">
            {user?.name?.charAt(0).toUpperCase() ?? 'U'}
          </AvatarFallback>
        </Avatar>
        {!collapsed && (
          <>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium truncate">{user?.name}</p>
              <p className="text-[10px] text-muted-foreground truncate">{user?.email}</p>
            </div>
            <Button variant="ghost" size="icon" className="w-7 h-7 text-muted-foreground hover:text-destructive" onClick={handleLogout}>
              <LogOut className="w-3.5 h-3.5" />
            </Button>
          </>
        )}
      </div>
    </motion.div>
  )
}
