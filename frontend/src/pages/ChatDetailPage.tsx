import { useState, useRef, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import { Trash2, Zap, BookOpen, ChevronRight, ChevronLeft, Brain } from 'lucide-react'
import { useMessages } from '@/api/messages'
import { streamMessage } from '@/api/messages'
import { useChat, useClearKnowledge } from '@/api/chats'
import { useGenerateQuiz, useSubmitQuiz, useRecommendations } from '@/api/quiz'
import { DocumentList } from '@/components/documents/DocumentList'
import { DropZone } from '@/components/documents/DropZone'
import { MessageBubble, StreamingBubble } from '@/components/chat/MessageBubble'
import { ChatInput } from '@/components/chat/ChatInput'
import { QuizCard, QuizResults } from '@/components/quiz/QuizCard'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/use-toast'
import { useQueryClient } from '@tanstack/react-query'
import type { Quiz, QuizResult } from '@/types'

export function ChatDetailPage() {
  const { chatId } = useParams<{ chatId: string }>()
  const { data: chatData } = useChat(chatId!)
  const { data: messagesData } = useMessages(chatId!)
  const clearKnowledge = useClearKnowledge()
  const generateQuiz = useGenerateQuiz(chatId!)
  const submitQuiz = useSubmitQuiz()
  const { data: recData, refetch: refetchRecs } = useRecommendations(chatId!, { enabled: false })
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [streamingContent, setStreamingContent] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [rightPanelOpen, setRightPanelOpen] = useState(true)
  const [quizTopic, setQuizTopic] = useState('')
  const [activeQuiz, setActiveQuiz] = useState<Quiz | null>(null)
  const [quizResult, setQuizResult] = useState<QuizResult | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messages = messagesData?.messages ?? []

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  const handleSend = async (content: string) => {
    if (!chatId) return
    setIsStreaming(true)
    setStreamingContent('')

    try {
      await streamMessage(
        chatId,
        content,
        (token) => setStreamingContent((prev) => (prev ?? '') + token),
        async () => {
          await queryClient.invalidateQueries({ queryKey: ['messages', chatId] })
          setStreamingContent(null)
          setIsStreaming(false)
        },
        () => {
          setStreamingContent(null)
          setIsStreaming(false)
          toast({ title: 'Error', description: 'Failed to get answer.', variant: 'destructive' })
        }
      )
    } catch {
      setStreamingContent(null)
      setIsStreaming(false)
    }
  }

  const handleGenerateQuiz = async () => {
    if (!quizTopic.trim() || !chatId) return
    try {
      const quiz = await generateQuiz.mutateAsync({ topic: quizTopic.trim(), num_questions: 5 })
      setActiveQuiz(quiz)
      setQuizResult(null)
    } catch {
      toast({ title: 'Quiz generation failed', description: 'Make sure you have documents uploaded.', variant: 'destructive' })
    }
  }

  const handleSubmitQuiz = async (answers: Record<string, string>) => {
    if (!activeQuiz) return
    try {
      const result = await submitQuiz.mutateAsync({ quizId: activeQuiz.id, answers })
      setQuizResult(result)
    } catch {
      toast({ title: 'Error', description: 'Failed to submit quiz.', variant: 'destructive' })
    }
  }

  const handleClearKnowledge = async () => {
    if (!chatId || !confirm('Are you sure? This will delete all AI knowledge from this chat.')) return
    try {
      await clearKnowledge.mutateAsync(chatId)
      toast({ description: 'Knowledge cleared.' })
    } catch {
      toast({ title: 'Error', description: 'Failed to clear knowledge.', variant: 'destructive' })
    }
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left Panel — Documents */}
      <div className="w-72 flex-shrink-0 flex flex-col border-r border-white/10 glass overflow-hidden">
        <div className="px-4 py-3 border-b border-white/10">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-foreground">Documents</h3>
            <Badge variant="secondary" className="text-[10px]">
              {messages.filter((m) => m.role === 'assistant').length} answers
            </Badge>
          </div>
        </div>
        <ScrollArea className="flex-1 p-3">
          <DocumentList chatId={chatId!} />
          <div className="mt-3">
            <DropZone chatId={chatId!} />
          </div>
        </ScrollArea>
        <div className="p-3 border-t border-white/10">
          <Button
            variant="ghost"
            size="sm"
            className="w-full text-xs text-destructive hover:text-destructive hover:bg-destructive/10 border border-destructive/20"
            onClick={handleClearKnowledge}
          >
            <Trash2 className="w-3.5 h-3.5 mr-1.5" />
            Clear Knowledge
          </Button>
        </div>
      </div>

      {/* Center — Chat */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3.5 border-b border-white/10 glass-card">
          <Brain className="w-5 h-5 text-purple-400" />
          <h2 className="text-sm font-semibold flex-1 truncate">{chatData?.title ?? 'Knowledge Space'}</h2>
        </div>

        {/* Messages */}
        <ScrollArea className="flex-1 px-5 py-4">
          <AnimatePresence>
            {messages.length === 0 && !isStreaming && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex flex-col items-center justify-center h-64 text-center gap-3"
              >
                <Brain className="w-10 h-10 text-muted-foreground opacity-30" />
                <p className="text-sm text-muted-foreground">Upload documents, then ask questions.</p>
                <p className="text-xs text-muted-foreground/60">Answers will cite the source and page.</p>
              </motion.div>
            )}
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {streamingContent !== null && (
              <StreamingBubble content={streamingContent} />
            )}
          </AnimatePresence>
          <div ref={messagesEndRef} />
        </ScrollArea>

        {/* Input */}
        <ChatInput onSend={handleSend} isStreaming={isStreaming} disabled={!chatId} />
      </div>

      {/* Right Panel — Quiz & Recommendations */}
      <motion.div
        animate={{ width: rightPanelOpen ? 320 : 0 }}
        transition={{ duration: 0.3 }}
        className="flex-shrink-0 flex flex-col border-l border-white/10 glass overflow-hidden"
      >
        {rightPanelOpen && (
          <div className="w-80 flex flex-col h-full overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
              <span className="text-xs font-semibold">Study Tools</span>
              <Button variant="ghost" size="icon" className="w-6 h-6" onClick={() => setRightPanelOpen(false)}>
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>

            <Tabs defaultValue="quiz" className="flex-1 flex flex-col overflow-hidden">
              <TabsList className="mx-3 mt-2 bg-white/5 h-8">
                <TabsTrigger value="quiz" className="text-[11px] flex-1">
                  <Zap className="w-3 h-3 mr-1" /> Quiz
                </TabsTrigger>
                <TabsTrigger value="recommendations" className="text-[11px] flex-1">
                  <BookOpen className="w-3 h-3 mr-1" /> Plan
                </TabsTrigger>
              </TabsList>

              <TabsContent value="quiz" className="flex-1 overflow-y-auto p-3 space-y-3">
                {!activeQuiz ? (
                  <div className="space-y-3">
                    <p className="text-[11px] text-muted-foreground">
                      Generate a quiz from your documents on any topic.
                    </p>
                    <Input
                      value={quizTopic}
                      onChange={(e) => setQuizTopic(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleGenerateQuiz()}
                      placeholder="e.g. Neural networks"
                      className="h-8 text-xs bg-white/5 border-white/10"
                    />
                    <Button
                      onClick={handleGenerateQuiz}
                      disabled={!quizTopic.trim() || generateQuiz.isPending}
                      className="w-full btn-gradient text-white border-0 h-8 text-xs"
                    >
                      {generateQuiz.isPending ? 'Generating…' : 'Generate Quiz'}
                    </Button>
                  </div>
                ) : quizResult ? (
                  <QuizResults
                    result={quizResult}
                    onRecommendations={() => refetchRecs()}
                    onRetry={() => { setActiveQuiz(null); setQuizResult(null) }}
                  />
                ) : (
                  <QuizCard
                    quiz={activeQuiz}
                    onSubmit={handleSubmitQuiz}
                    isSubmitting={submitQuiz.isPending}
                  />
                )}
              </TabsContent>

              <TabsContent value="recommendations" className="flex-1 overflow-y-auto p-3">
                {recData?.recommendations ? (
                  <div className="prose prose-sm prose-invert max-w-none">
                    <ReactMarkdown>{recData.recommendations}</ReactMarkdown>
                  </div>
                ) : (
                  <div className="text-center py-8">
                    <BookOpen className="w-8 h-8 text-muted-foreground/40 mx-auto mb-3" />
                    <p className="text-xs text-muted-foreground">Take a quiz first to get personalised recommendations.</p>
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </div>
        )}
      </motion.div>

      {/* Collapsed right panel toggle */}
      {!rightPanelOpen && (
        <Button
          variant="ghost"
          size="icon"
          className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8"
          onClick={() => setRightPanelOpen(true)}
        >
          <ChevronLeft className="w-4 h-4" />
        </Button>
      )}
    </div>
  )
}
