import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Sparkles,
  BookOpen,
  Search,
  RotateCw,
  Copy,
  Check,
  Tag,
  FileText,
  Lightbulb,
  Bookmark,
  FunctionSquare
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useToast } from '@/components/ui/use-toast'
import type { NotesResponse, NoteCard } from '@/types'

interface NotesCardsViewProps {
  notes: NotesResponse
  onRegenerate: () => void
  isRegenerating?: boolean
}

const tagBadgeStyle = (tag: string) => {
  switch (tag.toLowerCase()) {
    case 'definition':
      return { bg: 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300', icon: <BookOpen className="w-3 h-3" /> }
    case 'formula':
      return { bg: 'bg-cyan-500/15 border-cyan-500/30 text-cyan-300', icon: <FunctionSquare className="w-3 h-3" /> }
    case 'takeaway':
      return { bg: 'bg-amber-500/15 border-amber-500/30 text-amber-300', icon: <Lightbulb className="w-3 h-3" /> }
    case 'summary':
      return { bg: 'bg-indigo-500/15 border-indigo-500/30 text-indigo-300', icon: <Bookmark className="w-3 h-3" /> }
    default:
      return { bg: 'bg-purple-500/15 border-purple-500/30 text-purple-300', icon: <Sparkles className="w-3 h-3" /> }
  }
}

export function NotesCardsView({ notes, onRegenerate, isRegenerating }: NotesCardsViewProps) {
  const [search, setSearch] = useState('')
  const [selectedTag, setSelectedTag] = useState<string>('All')
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const { toast } = useToast()

  const allTags = ['All', ...Array.from(new Set(notes.cards.map((c) => c.tag)))]

  const filteredCards = notes.cards.filter((card) => {
    const matchesTag = selectedTag === 'All' || card.tag.toLowerCase() === selectedTag.toLowerCase()
    const matchesSearch =
      card.topic.toLowerCase().includes(search.toLowerCase()) ||
      card.summary.toLowerCase().includes(search.toLowerCase()) ||
      card.key_points.some((kp) => kp.toLowerCase().includes(search.toLowerCase()))
    return matchesTag && matchesSearch
  })

  const handleCopyCard = (card: NoteCard) => {
    const text = `📌 ${card.topic}\n\n${card.summary}\n\nKey Takeaways:\n${card.key_points.map((p) => `• ${p}`).join('\n')}\n\n[Source: ${card.source ?? 'Document'}, Page ${card.page ?? 1}]`
    navigator.clipboard.writeText(text)
    setCopiedId(card.id)
    toast({ description: 'Note card copied to clipboard.' })
    setTimeout(() => setCopiedId(null), 2000)
  }

  return (
    <div className="flex flex-col h-full w-full overflow-hidden">
      {/* Header Bar */}
      <div className="px-6 py-4 border-b border-white/10 glass-card flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 flex-shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-purple-400" />
            <h2 className="text-sm font-semibold text-foreground">{notes.title}</h2>
            <Badge variant="secondary" className="text-[10px]">
              {notes.cards.length} cards
            </Badge>
          </div>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Auto-synthesized key concepts from all uploaded documents in this chat.
          </p>
        </div>

        <Button
          size="sm"
          variant="outline"
          onClick={onRegenerate}
          disabled={isRegenerating}
          className="h-8 text-xs border-white/15 hover:bg-white/5"
        >
          <RotateCw className={`w-3.5 h-3.5 mr-1.5 ${isRegenerating ? 'animate-spin' : ''}`} />
          {isRegenerating ? 'Generating...' : 'Regenerate Notes'}
        </Button>
      </div>

      {/* Filter and Search Bar */}
      <div className="px-6 py-3 border-b border-white/10 bg-white/3 flex flex-wrap items-center justify-between gap-3 flex-shrink-0">
        {/* Category Tag Pills */}
        <div className="flex items-center gap-1.5 overflow-x-auto py-1">
          {allTags.map((tag) => (
            <button
              key={tag}
              onClick={() => setSelectedTag(tag)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-all ${selectedTag === tag
                  ? 'bg-purple-600 text-white shadow-md shadow-purple-500/20'
                  : 'bg-white/5 text-muted-foreground hover:bg-white/10 hover:text-foreground border border-white/10'
                }`}
            >
              {tag}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative w-full sm:w-60">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search note cards..."
            className="pl-8 h-8 text-xs bg-white/5 border-white/10"
          />
        </div>
      </div>

      {/* Notes Cards Scroll Area */}
      <ScrollArea className="flex-1 p-6">
        {filteredCards.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <Tag className="w-10 h-10 text-muted-foreground opacity-30 mb-2" />
            <p className="text-sm text-muted-foreground">No note cards match your search filter.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pb-6">
            <AnimatePresence>
              {filteredCards.map((card, index) => {
                const tagStyle = tagBadgeStyle(card.tag)
                return (
                  <motion.div
                    key={card.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.05 }}
                    className="glass-card rounded-2xl p-5 border border-white/10 hover:border-purple-500/40 transition-all flex flex-col justify-between group shadow-lg"
                  >
                    <div>
                      {/* Top Bar */}
                      <div className="flex items-center justify-between gap-2 mb-3">
                        <Badge className={`text-[10px] gap-1 px-2.5 py-0.5 border ${tagStyle.bg}`}>
                          {tagStyle.icon}
                          {card.tag}
                        </Badge>

                        <Button
                          variant="ghost"
                          size="icon"
                          className="w-7 h-7 text-muted-foreground hover:text-foreground opacity-70 group-hover:opacity-100"
                          onClick={() => handleCopyCard(card)}
                          title="Copy card"
                        >
                          {copiedId === card.id ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
                        </Button>
                      </div>

                      {/* Topic Title */}
                      <h3 className="text-sm font-bold text-foreground mb-2 leading-snug">{card.topic}</h3>

                      {/* Summary */}
                      <p className="text-xs text-muted-foreground mb-4 leading-relaxed bg-white/5 p-2.5 rounded-xl border border-white/5">
                        {card.summary}
                      </p>

                      {/* Key Points */}
                      <div className="space-y-1.5 mb-4">
                        <h4 className="text-[11px] font-semibold text-purple-300 uppercase tracking-wider">Key Takeaways</h4>
                        <ul className="space-y-1">
                          {card.key_points.map((point, idx) => (
                            <li key={idx} className="text-xs text-foreground/90 flex items-start gap-2 leading-normal">
                              <span className="w-1.5 h-1.5 rounded-full bg-purple-400 mt-1.5 flex-shrink-0" />
                              <span>{point}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    {/* Footer Citation */}
                    <div className="pt-3 border-t border-white/10 flex items-center justify-between text-[10px] text-muted-foreground">
                      <span className="flex items-center gap-1 truncate max-w-[80%]" title={card.source}>
                        <FileText className="w-3 h-3 text-purple-400 flex-shrink-0" />
                        <span className="truncate">{card.source}</span>
                      </span>
                      <span>Page {card.page ?? 1}</span>
                    </div>
                  </motion.div>
                )
              })}
            </AnimatePresence>
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
