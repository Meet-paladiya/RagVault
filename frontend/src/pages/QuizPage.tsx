import { motion } from 'framer-motion'
import { History, Zap } from 'lucide-react'
import { useChats } from '@/api/chats'
import { useQuizHistory } from '@/api/quiz'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { formatDistanceToNow } from 'date-fns'

export function QuizPage() {
  const { data: chatsData } = useChats()
  const chats = chatsData?.chats ?? []

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <div className="px-6 py-5 border-b border-white/10">
        <div className="flex items-center gap-2">
          <History className="w-5 h-5 text-primary" />
          <h1 className="text-lg font-semibold">Quiz History</h1>
        </div>
        <p className="text-xs text-muted-foreground mt-1">All your quiz results across knowledge spaces</p>
      </div>

      <ScrollArea className="flex-1 px-6 py-4">
        {chats.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <History className="w-12 h-12 mx-auto mb-3 opacity-20" />
            <p className="text-sm">No quizzes yet. Create a knowledge space and take a quiz!</p>
          </div>
        ) : (
          <div className="space-y-6">
            {chats.map((chat) => (
              <ChatQuizSection key={chat.id} chatId={chat.id} chatTitle={chat.title} />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}

function ChatQuizSection({ chatId, chatTitle }: { chatId: string; chatTitle: string }) {
  const { data } = useQuizHistory(chatId)
  const quizzes = data ?? []

  if (quizzes.length === 0) return null

  return (
    <div>
      <h2 className="text-sm font-semibold mb-3 text-muted-foreground">{chatTitle}</h2>
      <div className="grid gap-3">
        {quizzes.map((quiz) => {
          const score = quiz.score ?? null
          const pct = score != null ? Math.round(score) : null
          return (
            <motion.div
              key={quiz.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card rounded-xl p-4 flex items-center gap-4"
            >
              {/* Score Circle */}
              <div className={`w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0 text-sm font-bold ${pct == null ? 'bg-white/10 text-muted-foreground'
                  : pct >= 80 ? 'bg-success/20 text-success'
                    : pct >= 50 ? 'bg-primary/20 text-primary'
                      : 'bg-destructive/20 text-destructive'
                }`}>

              </div>

              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5 text-primary" />
                  {quiz.topic}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {quiz.total_questions} questions · {formatDistanceToNow(new Date(quiz.created_at), { addSuffix: true })}
                </p>
                {quiz.weak_topics && quiz.weak_topics.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {quiz.weak_topics.slice(0, 3).map((t: string, i: number) => (
                      <Badge key={i} className="text-[10px] bg-orange-500/10 text-orange-400 border-orange-500/20">
                        {t.length > 30 ? t.slice(0, 30) + '…' : t}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}
