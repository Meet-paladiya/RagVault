import { useRef, useState, useCallback, useEffect } from 'react'
import { motion } from 'framer-motion'
import { SendHorizonal, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface ChatInputProps {
  onSend: (content: string) => void
  onStop?: () => void
  disabled?: boolean
  isStreaming?: boolean
  disabledMessage?: string
}

export function ChatInput({ onSend, onStop, disabled, isStreaming, disabledMessage }: ChatInputProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const adjustHeight = useCallback(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`
  }, [])

  useEffect(() => { adjustHeight() }, [value, adjustHeight])

  const handleSend = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled || isStreaming) return
    onSend(trimmed)
    setValue('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <motion.div
      initial={{ y: 20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="px-4 pb-4"
    >
      {/* Floating Stop Generating indicator when streaming */}
      {isStreaming && onStop && (
        <div className="flex justify-center mb-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onStop}
            className="h-7 text-xs px-3.5 bg-destructive/15 border border-destructive/40 text-destructive-foreground hover:bg-destructive/25 shadow-lg rounded-full flex items-center gap-1.5 cursor-pointer transition-all animate-pulse"
          >
            <Square className="w-3 h-3 fill-current" />
            <span>Stop Generating</span>
          </Button>
        </div>
      )}

      <div className="glass chat-input-container rounded-2xl border border-white/15 flex items-end gap-2 p-2 shadow-2xl focus-within:border-purple-500/50 transition-colors duration-200">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled || isStreaming}
          placeholder="Ask a question about your documents… (Enter to send, Shift+Enter for new line)"
          rows={1}
          className="flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none py-2 px-2 max-h-40 leading-relaxed"
        />
        {isStreaming ? (
          <Button
            type="button"
            onClick={onStop}
            className="h-9 px-3 text-xs bg-destructive text-white hover:bg-destructive/90 border-0 rounded-xl flex items-center gap-1.5 flex-shrink-0 cursor-pointer shadow-md"
            title="Stop generating"
          >
            <Square className="w-3.5 h-3.5 fill-current" />
            <span className="font-semibold text-xs">Stop</span>
          </Button>
        ) : (
          <Button
            size="icon"
            onClick={handleSend}
            disabled={!value.trim() || disabled}
            className="h-9 w-9 flex-shrink-0 btn-gradient text-white border-0 disabled:opacity-40 rounded-xl"
          >
            <SendHorizonal className="w-4 h-4" />
          </Button>
        )}
      </div>
      {disabledMessage && disabled && !isStreaming && (
        <p className="text-[10px] text-amber-400 text-center mt-1.5">{disabledMessage}</p>
      )}
      <p className="text-[10px] text-muted-foreground text-center mt-1.5">
        Enter to send · Shift+Enter for new line · Answers grounded in your documents
      </p>
    </motion.div>
  )
}

