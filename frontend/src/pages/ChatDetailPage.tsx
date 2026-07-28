import { useState, useRef, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Trash2, Zap, ChevronRight, ChevronLeft, Brain, MessageSquare, BookOpen, Sparkles, RotateCw
} from 'lucide-react'
import { useMessages, streamMessage } from '@/api/messages'
import { useChat, useClearKnowledge } from '@/api/chats'
import { useGenerateQuiz, useSubmitQuiz } from '@/api/quiz'
import { useNotes, useGenerateNotes } from '@/api/notes'
import { DocumentList } from '@/components/documents/DocumentList'
import { DropZone } from '@/components/documents/DropZone'
import { MessageBubble, StreamingBubble } from '@/components/chat/MessageBubble'
import { ChatInput } from '@/components/chat/ChatInput'
import { QuizCard, QuizResults } from '@/components/quiz/QuizCard'
import { NotesGeneratingGraphic } from '@/components/notes/NotesGeneratingGraphic'
import { NotesCardsView } from '@/components/notes/NotesCardsView'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/use-toast'
import { useQueryClient } from '@tanstack/react-query'
import type { Quiz, QuizResult } from '@/types'

export function ChatDetailPage() {
  const { chatId } = useParams<{ chatId: string }>()
  const navigate = useNavigate()
  const { data: chatData, isError: isChatError } = useChat(chatId!)

  useEffect(() => {
    if (isChatError) {
      navigate('/chats', { replace: true })
    }
  }, [isChatError, navigate])

  const abortControllerRef = useRef<AbortController | null>(null)

  const [centerViewMode, setCenterViewMode] = useState<'chat' | 'notes'>('chat')
  const [rhsTab, setRhsTab] = useState<'quiz' | 'notes'>('quiz')

  useEffect(() => {
    // Abort active stream from previous chat on chatId change
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }

    setStreamingContent(null)
    setOptimisticUserMessage(null)
    setIsStreaming(false)
    setActiveQuiz(null)
    setQuizResult(null)
    setSelectedQuizType(null)
    setCenterViewMode('chat')
    setRhsTab('quiz')

    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
        abortControllerRef.current = null
      }
    }
  }, [chatId])

  const { data: messagesData } = useMessages(chatId!)
  const { data: notesData } = useNotes(chatId!)
  const generateNotes = useGenerateNotes(chatId!)
  const clearKnowledge = useClearKnowledge()
  const generateQuiz = useGenerateQuiz(chatId!)
  const submitQuiz = useSubmitQuiz()
  const { toast } = useToast()
  const queryClient = useQueryClient()

  const [streamingContent, setStreamingContent] = useState<string | null>(null)
  const [optimisticUserMessage, setOptimisticUserMessage] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [rightPanelOpen, setRightPanelOpen] = useState(true)
  const [quizTopic, setQuizTopic] = useState('')
  const [selectedQuizType, setSelectedQuizType] = useState<'auto' | 'topic' | null>(null)
  const [activeQuiz, setActiveQuiz] = useState<Quiz | null>(null)
  const [quizResult, setQuizResult] = useState<QuizResult | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const messages = messagesData?.messages ?? []

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent, optimisticUserMessage])

  const handleSend = async (content: string) => {
    if (!chatId) return

    // Cancel any existing in-flight stream
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const controller = new AbortController()
    abortControllerRef.current = controller

    setIsStreaming(true)
    setOptimisticUserMessage(content)
    setStreamingContent('')

    try {
      await streamMessage(
        chatId,
        content,
        (token) => {
          if (!controller.signal.aborted) {
            setStreamingContent((prev) => (prev ?? '') + token)
          }
        },
        async () => {
          if (!controller.signal.aborted) {
            await queryClient.invalidateQueries({ queryKey: ['messages', chatId] })
            setOptimisticUserMessage(null)
            setStreamingContent(null)
            setIsStreaming(false)
          }
        },
        () => {
          if (!controller.signal.aborted) {
            setOptimisticUserMessage(null)
            setStreamingContent(null)
            setIsStreaming(false)
            toast({ title: 'Error', description: 'Failed to get answer.', variant: 'destructive' })
          }
        },
        controller.signal,
      )
    } catch {
      if (!controller.signal.aborted) {
        setOptimisticUserMessage(null)
        setStreamingContent(null)
        setIsStreaming(false)
      }
    }
  }

  const handleOpenNotes = async () => {
    setCenterViewMode('notes')
    if (!notesData && !generateNotes.isPending) {
      try {
        await generateNotes.mutateAsync()
      } catch {
        toast({ title: 'Generation error', description: 'Make sure documents are uploaded.', variant: 'destructive' })
      }
    }
  }

  const handleGenerateQuiz = async (type: 'auto' | 'topic', topicOverride?: string) => {
    if (!chatId) return
    setSelectedQuizType(type)
    const topic = type === 'auto' ? 'General Summary' : (topicOverride || 'General Summary')
    try {
      const quiz = await generateQuiz.mutateAsync({ topic, num_questions: 20 })
      setActiveQuiz(quiz)
      setQuizResult(null)
    } catch {
      toast({ title: 'Quiz generation failed', description: 'Make sure you have documents uploaded.', variant: 'destructive' })
      setSelectedQuizType(null)
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
      <div className="w-72 min-w-[288px] max-w-[288px] flex-shrink-0 flex flex-col border-r border-white/10 glass overflow-hidden">
        <div className="px-4 py-3 border-b border-white/10 flex-shrink-0">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-foreground">Documents</h3>
            <Badge variant="secondary" className="text-[10px]">
              {messages.filter((m) => m.role === 'assistant').length} answers
            </Badge>
          </div>
        </div>

        {/* Scrollable document list */}
        <div className="flex-1 min-h-0 overflow-y-auto p-3">
          <DocumentList chatId={chatId!} />
        </div>

        {/* Fixed DropZone */}
        <div className="p-3 border-t border-white/10 flex-shrink-0">
          <DropZone chatId={chatId!} />
        </div>

        {/* Clear Knowledge Footer */}
        <div className="p-3 border-t border-white/10 flex-shrink-0">
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

      {/* Center Section — Dynamic View (Chat or AI Notes) */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/10 glass-card flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <Brain className="w-5 h-5 text-purple-400 flex-shrink-0" />
            <h2 className="text-sm font-semibold truncate">{chatData?.title ?? 'Knowledge Space'}</h2>
          </div>

          {/* View Mode Toggle Buttons */}
          <div className="flex items-center gap-1 bg-white/5 p-1 rounded-xl border border-white/10 flex-shrink-0">
            <Button
              variant={centerViewMode === 'chat' ? 'secondary' : 'ghost'}
              size="sm"
              className="h-7 text-xs px-3"
              onClick={() => setCenterViewMode('chat')}
            >
              <MessageSquare className="w-3.5 h-3.5 mr-1.5" />
              Chat
            </Button>
            <Button
              variant={centerViewMode === 'notes' ? 'secondary' : 'ghost'}
              size="sm"
              className="h-7 text-xs px-3"
              onClick={handleOpenNotes}
            >
              <Sparkles className="w-3.5 h-3.5 mr-1.5 text-purple-400" />
              AI Notes
            </Button>
          </div>
        </div>

        {/* Center Main Content Area */}
        {centerViewMode === 'notes' ? (
          <div className="flex-1 overflow-hidden">
            {generateNotes.isPending ? (
              <NotesGeneratingGraphic />
            ) : notesData ? (
              <NotesCardsView
                notes={notesData}
                onRegenerate={() => generateNotes.mutateAsync()}
                isRegenerating={generateNotes.isPending}
              />
            ) : (
              <div className="flex flex-col items-center justify-center h-full p-8 text-center">
                <BookOpen className="w-12 h-12 text-purple-400/40 mb-4" />
                <h3 className="text-base font-semibold mb-2">No AI Notes Generated Yet</h3>
                <p className="text-xs text-muted-foreground max-w-sm mb-6 leading-relaxed">
                  Synthesize key concepts, definitions, formulas, and takeaways into high-yield study cards from your documents.
                </p>
                <Button
                  onClick={() => generateNotes.mutateAsync()}
                  disabled={generateNotes.isPending}
                  className="btn-gradient text-white border-0 px-6 py-2.5 text-xs rounded-xl"
                >
                  <Sparkles className="w-4 h-4 mr-2" />
                  Generate AI Notes
                </Button>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* Messages View */}
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
                {optimisticUserMessage && (
                  <MessageBubble
                    message={{
                      id: 'temp-optimistic-user',
                      chat_id: chatId!,
                      role: 'user',
                      content: optimisticUserMessage,
                      citations: [],
                      created_at: new Date().toISOString(),
                    }}
                  />
                )}
                {streamingContent !== null && (
                  <StreamingBubble content={streamingContent} />
                )}
              </AnimatePresence>
              <div ref={messagesEndRef} />
            </ScrollArea>

            {/* Input */}
            <ChatInput onSend={handleSend} isStreaming={isStreaming} disabled={!chatId} />
          </>
        )}
      </div>

      {/* Right Panel — Quiz & AI Notes RHS */}
      <motion.div
        animate={{ width: rightPanelOpen ? 320 : 0 }}
        transition={{ duration: 0.3 }}
        className="flex-shrink-0 flex flex-col border-l border-white/10 glass overflow-hidden"
      >
        {rightPanelOpen && (
          <div className="w-80 flex flex-col h-full overflow-hidden">
            {/* RHS Panel Header with Quiz / Notes Tabs */}
            <div className="flex items-center justify-between px-3 py-2.5 border-b border-white/10 flex-shrink-0">
              <div className="flex items-center gap-1 bg-white/5 p-0.5 rounded-lg border border-white/10">
                <button
                  onClick={() => setRhsTab('quiz')}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition-colors ${
                    rhsTab === 'quiz' ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Zap className="w-3.5 h-3.5" />
                  Quiz
                </button>
                <button
                  onClick={() => {
                    setRhsTab('notes')
                    handleOpenNotes()
                  }}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition-colors ${
                    rhsTab === 'notes' ? 'bg-purple-500/20 text-purple-300' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                  AI Notes
                </button>
              </div>

              <Button variant="ghost" size="icon" className="w-6 h-6" onClick={() => setRightPanelOpen(false)}>
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>

            {/* RHS Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {rhsTab === 'notes' ? (
                /* RHS AI Notes Card Summary */
                <div className="space-y-4">
                  <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3">
                    <div className="flex items-center gap-2">
                      <BookOpen className="w-4 h-4 text-purple-400" />
                      <h4 className="text-xs font-semibold">AI Study Notes Cards</h4>
                    </div>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      Generates structured study cards for all uploaded documents in this Knowledge Space.
                    </p>

                    <Button
                      onClick={handleOpenNotes}
                      disabled={generateNotes.isPending}
                      className="w-full btn-gradient text-white border-0 h-8 text-xs rounded-lg mt-1"
                    >
                      {generateNotes.isPending ? (
                        <>
                          <RotateCw className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                          Generating Cards...
                        </>
                      ) : notesData ? (
                        'View Notes Cards'
                      ) : (
                        'Generate AI Notes'
                      )}
                    </Button>
                  </div>

                  {notesData && (
                    <div className="bg-purple-950/20 border border-purple-500/20 rounded-xl p-3.5 space-y-2">
                      <div className="flex items-center justify-between text-xs text-purple-300 font-medium">
                        <span>Latest Notes</span>
                        <Badge variant="secondary" className="text-[9px]">
                          {notesData.cards.length} cards
                        </Badge>
                      </div>
                      <p className="text-[11px] text-muted-foreground truncate">{notesData.title}</p>
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full h-7 text-[11px] border-white/10"
                        onClick={handleOpenNotes}
                      >
                        Open Cards View →
                      </Button>
                    </div>
                  )}
                </div>
              ) : (
                /* RHS Quiz Content */
                !activeQuiz ? (
                  <div className="flex flex-col gap-4 py-2">
                    <div className="text-center mb-2 flex items-center justify-between">
                      <div className="text-left">
                        <h4 className="text-sm font-semibold">Start a Quiz</h4>
                        <p className="text-[11px] text-muted-foreground leading-relaxed">
                          Generate a 20-question custom quiz (10 MCQs + 10 Fill in the blanks).
                        </p>
                      </div>
                      {selectedQuizType && !generateQuiz.isPending && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-[10px] h-6 px-2 text-muted-foreground hover:text-foreground"
                          onClick={() => setSelectedQuizType(null)}
                        >
                          Reset
                        </Button>
                      )}
                    </div>

                    {/* Section 1: Auto Quiz */}
                    {selectedQuizType !== 'topic' && (
                      <div className="bg-white/5 border border-white/10 rounded-xl p-3.5 flex flex-col gap-2.5 shadow-sm">
                        <div className="flex items-center gap-1.5">
                          <Brain className="w-4 h-4 text-purple-400" />
                          <h5 className="text-xs font-semibold">Auto Quiz (All Docs)</h5>
                        </div>
                        <p className="text-[10px] text-muted-foreground leading-relaxed">
                          Builds a general 20-question quiz (10 MCQs + 10 Fill-in-blanks) covering all documents.
                        </p>
                        <Button
                          onClick={() => handleGenerateQuiz('auto', 'General Summary')}
                          disabled={generateQuiz.isPending}
                          className="w-full btn-gradient text-white border-0 h-8 text-[11px] rounded-lg mt-1"
                        >
                          {generateQuiz.isPending && selectedQuizType === 'auto'
                            ? 'Generating 20 Questions…'
                            : 'Generate Auto Quiz'}
                        </Button>
                      </div>
                    )}

                    {/* Section 2: Topic Quiz */}
                    {selectedQuizType !== 'auto' && (
                      <div className="bg-white/5 border border-white/10 rounded-xl p-3.5 flex flex-col gap-2.5 shadow-sm">
                        <div className="flex items-center gap-1.5">
                          <Zap className="w-4 h-4 text-purple-400" />
                          <h5 className="text-xs font-semibold">Topic Quiz</h5>
                        </div>
                        <p className="text-[10px] text-muted-foreground leading-relaxed">
                          Focuses specifically on a chosen subject or chapter (10 MCQs + 10 Fill-in-blanks).
                        </p>
                        <div className="space-y-2 mt-1">
                          <Input
                            value={quizTopic}
                            onChange={(e) => setQuizTopic(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && handleGenerateQuiz('topic', quizTopic)}
                            placeholder="e.g. Neural networks"
                            disabled={generateQuiz.isPending}
                            className="h-8 text-xs bg-white/5 border-white/10 focus-visible:ring-1 focus-visible:ring-purple-500/50"
                          />
                          <Button
                            onClick={() => handleGenerateQuiz('topic', quizTopic)}
                            disabled={!quizTopic.trim() || generateQuiz.isPending}
                            className="w-full btn-gradient text-white border-0 h-8 text-[11px] rounded-lg"
                          >
                            {generateQuiz.isPending && selectedQuizType === 'topic'
                              ? 'Generating 20 Questions…'
                              : 'Generate Topic Quiz'}
                          </Button>
                        </div>
                      </div>
                    )}

                    {selectedQuizType && generateQuiz.isPending && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-xs text-muted-foreground hover:text-foreground border border-white/10"
                        onClick={() => setSelectedQuizType(null)}
                      >
                        Cancel / Show All Options
                      </Button>
                    )}
                  </div>
                ) : quizResult ? (
                  <QuizResults
                    result={quizResult}
                    onRecommendations={() => { }}
                    onRetry={() => { setActiveQuiz(null); setQuizResult(null); setSelectedQuizType(null) }}
                  />
                ) : (
                  <div className="space-y-3">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-[11px] h-7 text-muted-foreground hover:text-foreground px-2"
                      onClick={() => { setActiveQuiz(null); setQuizResult(null); setSelectedQuizType(null) }}
                    >
                      ← Exit Quiz
                    </Button>
                    <QuizCard
                      quiz={activeQuiz}
                      onSubmit={handleSubmitQuiz}
                      isSubmitting={submitQuiz.isPending}
                    />
                  </div>
                )
              )}
            </div>
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
