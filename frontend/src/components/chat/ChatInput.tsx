import { useRef, useState, useCallback, useEffect } from 'react'
import { motion } from 'framer-motion'
import { SendHorizonal, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface ChatInputProps {
  onSend: (content: string) => void
  disabled?: boolean
  isStreaming?: boolean
}

export function ChatInput({ onSend, disabled, isStreaming }: ChatInputProps) {
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
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
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
      <div className="glass rounded-2xl border border-white/15 flex items-end gap-2 p-2 shadow-2xl focus-within:border-purple-500/50 transition-colors duration-200">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled || isStreaming}
          placeholder="Ask a question about your documents… (Ctrl+Enter to send)"
          rows={1}
          className="flex-1 resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none py-2 px-2 max-h-40 leading-relaxed"
        />
        <Button
          size="icon"
          onClick={handleSend}
          disabled={!value.trim() || disabled || isStreaming}
          className="h-9 w-9 flex-shrink-0 btn-gradient text-white border-0 disabled:opacity-40 rounded-xl"
        >
          {isStreaming
            ? <Loader2 className="w-4 h-4 animate-spin" />
            : <SendHorizonal className="w-4 h-4" />}
        </Button>
      </div>
      <p className="text-[10px] text-muted-foreground text-center mt-1.5">
        Ctrl+Enter to send · Answers grounded in your uploaded documents
      </p>
    </motion.div>
  )
}
