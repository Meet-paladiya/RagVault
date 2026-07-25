import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { BookOpen, ChevronDown, ChevronUp, User, Brain, Copy, Check } from 'lucide-react'
import { format, isToday, isYesterday } from 'date-fns'
import type { Message, Citation } from '@/types'
import { Badge } from '@/components/ui/badge'

interface MessageBubbleProps {
  message: Message
}

function formatMessageTime(dateStr: string): string {
  if (!dateStr) return ''
  const str = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z'
  const date = new Date(str)
  if (isNaN(date.getTime())) return ''
  
  if (isToday(date)) {
    return format(date, 'h:mm a')
  }
  if (isYesterday(date)) {
    return `Yesterday, ${format(date, 'h:mm a')}`
  }
  return format(date, 'MMM d, h:mm a')
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const [citationsOpen, setCitationsOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const citations: Citation[] = message.citations ?? []

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // ignore
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={`flex gap-3 mb-4 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      {/* Avatar */}
      <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
        isUser
          ? 'bg-gradient-to-br from-purple-500 to-indigo-600'
          : 'bg-white/10 border border-white/20'
      }`}>
        {isUser ? <User className="w-4 h-4 text-white" /> : <Brain className="w-4 h-4 text-purple-400" />}
      </div>

      <div className={`flex flex-col max-w-[78%] ${isUser ? 'items-end' : 'items-start'}`}>
        {/* Bubble */}
        <div className={`group relative rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-gradient-to-br from-purple-600 to-indigo-700 text-white rounded-tr-sm'
            : 'glass-card text-foreground rounded-tl-sm'
        }`}>
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ node, inline, className, children, ...props }: any) {
                  const match = /language-(\w+)/.exec(className || '')
                  return !inline && match ? (
                    <SyntaxHighlighter style={oneDark} language={match[1]} PreTag="div" {...props}>
                      {String(children).replace(/\n$/, '')}
                    </SyntaxHighlighter>
                  ) : (
                    <code className="bg-white/10 px-1.5 py-0.5 rounded text-xs font-mono" {...props}>
                      {children}
                    </code>
                  )
                },
                p({ children }) { return <p className="mb-2 last:mb-0">{children}</p> },
                ul({ children }) { return <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul> },
                ol({ children }) { return <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol> },
                h3({ children }) { return <h3 className="font-semibold text-sm mb-1">{children}</h3> },
              }}
            >
              {message.content}
            </ReactMarkdown>
          )}
        </div>

        {/* Citations */}
        {!isUser && citations.length > 0 && (
          <div className="mt-1.5 w-full">
            <button
              onClick={() => setCitationsOpen((v) => !v)}
              className="flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-purple-400 transition-colors"
            >
              <BookOpen className="w-3 h-3" />
              <span>{citations.length} source{citations.length > 1 ? 's' : ''}</span>
              {citationsOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>

            <AnimatePresence>
              {citationsOpen && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mt-1.5 flex flex-wrap gap-1.5 overflow-hidden"
                >
                  {citations.map((c, i) => (
                    <Badge
                      key={i}
                      variant="secondary"
                      className="text-[10px] bg-purple-500/15 text-purple-300 border border-purple-500/30 px-2 py-0.5"
                    >
                      {c.source} · p.{c.page}
                    </Badge>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {/* Timestamp and Copy button */}
        <div className={`flex items-center gap-2 mt-1 px-1 text-[10px] text-muted-foreground ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
          <span>{formatMessageTime(message.created_at)}</span>
          <button
            onClick={handleCopy}
            title="Copy message"
            className="hover:text-purple-300 transition-colors p-0.5 rounded opacity-70 hover:opacity-100 flex items-center gap-0.5"
          >
            {copied ? (
              <>
                <Check className="w-3 h-3 text-green-400" />
                <span className="text-[9px] text-green-400 font-medium">Copied</span>
              </>
            ) : (
              <Copy className="w-3 h-3" />
            )}
          </button>
        </div>
      </div>
    </motion.div>
  )
}

export function StreamingBubble({ content }: { content: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-3 mb-4"
    >
      <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-white/10 border border-white/20">
        <Brain className="w-4 h-4 text-purple-400 animate-pulse" />
      </div>
      <div className="glass-card rounded-2xl rounded-tl-sm px-4 py-3 text-sm max-w-[78%]">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content || '▍'}</ReactMarkdown>
      </div>
    </motion.div>
  )
}
