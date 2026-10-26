import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Sparkles, RotateCw, Copy, Check, FileText, Search, Download
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
  onDownloadPdf: () => Promise<void>
  isRegenerating?: boolean
  isDownloadingPdf?: boolean
}

function cleanTopicTitle(topic?: string): string {
  if (!topic) return 'Key Concepts'
  const cleaned = topic
    .replace(/[:\-–—]?\s*\(?pages?\s*\d+([–\-]\d+)?\)?/gi, '')
    .replace(/\bpage\s*\d+\b/gi, '')
    .replace(/\b(summary|overview)\b/gi, '')
    .trim()
  return cleaned.length >= 3 ? cleaned : topic.trim()
}

export function NotesCardsView({ notes, onRegenerate, onDownloadPdf, isRegenerating, isDownloadingPdf }: NotesCardsViewProps) {
  const [search, setSearch] = useState('')
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const { toast } = useToast()

  const filteredCards = notes.cards.filter((card) => {
    const cleanTopic = cleanTopicTitle(card.topic).toLowerCase()
    const matchesSearch =
      cleanTopic.includes(search.toLowerCase()) ||
      card.summary.toLowerCase().includes(search.toLowerCase()) ||
      card.key_points.some((kp) => kp.toLowerCase().includes(search.toLowerCase()))
    return matchesSearch
  })

  const handleCopyCard = (card: NoteCard) => {
    const topic = cleanTopicTitle(card.topic)
    const text = `📌 ${topic}\n\n${card.summary}\n\nKey Points:\n${card.key_points.map((p) => `• ${p}`).join('\n')}\n\n[Source: ${card.source ?? 'Document'}]`
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
            <Sparkles className="w-4 h-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">{notes.title} - High-Yield Study Notes</h2>
            <Badge variant="secondary" className="text-[10px]">
              {notes.cards.length} topics
            </Badge>
          </div>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Consolidated 2-page revision summary covering all major concepts. Download separate PDFs in a ZIP archive.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={onDownloadPdf}
            disabled={isDownloadingPdf}
            className="h-8 text-xs border-primary/50 hover:border-primary px-3 bg-primary/10 hover:bg-primary/20 text-foreground"
          >
            <Download className="w-3.5 h-3.5 mr-1.5 text-primary" />
            {isDownloadingPdf ? 'Preparing Notes...' : 'Download Notes (ZIP)'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={onRegenerate}
            disabled={isRegenerating}
            className="h-8 text-xs border-white/20 px-3"
          >
            <RotateCw className={`w-3.5 h-3.5 mr-1.5 ${isRegenerating ? 'animate-spin' : ''}`} />
            {isRegenerating ? 'Generating...' : 'Regenerate'}
          </Button>
        </div>
      </div>

      {/* Search Bar */}
      <div className="px-6 py-3 border-b border-white/10 bg-white/3 flex items-center justify-between gap-3 flex-shrink-0">
        <div className="text-xs text-muted-foreground font-medium">
          Key Topics ({filteredCards.length})
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search topics, formulas, concepts..."
            className="pl-8 h-8 text-xs bg-white/5 border-white/10 rounded-lg"
          />
        </div>
      </div>

      {/* Cards Grid Container */}
      <ScrollArea className="flex-1 p-6">
        {filteredCards.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <Search className="w-10 h-10 text-muted-foreground opacity-30 mb-2" />
            <p className="text-sm text-muted-foreground">No note cards match your search query.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pb-6">
            <AnimatePresence>
              {filteredCards.map((card, index) => {
                const topic = cleanTopicTitle(card.topic)
                const chapter = cleanTopicTitle(card.chapter)
                const showChapter = chapter && !['summary', 'general', 'overview', 'chapter overview'].includes(chapter.toLowerCase())

                return (
                  <motion.div
                    key={card.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.05 }}
                    className="glass-card rounded-2xl p-5 border border-white/10 hover:border-primary/40 transition-all flex flex-col justify-between group shadow-lg"
                  >
                    <div>
                      {showChapter && (
                        <div className="mb-1.5 flex items-center gap-1.5">
                          <Badge variant="outline" className="text-[9px] uppercase px-1.5 py-0 border-primary/30 text-primary font-mono">
                            {chapter}
                          </Badge>
                        </div>
                      )}
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <h3 className="text-sm font-bold text-foreground leading-snug flex-1">{topic}</h3>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="w-7 h-7 text-muted-foreground hover:text-foreground opacity-70 group-hover:opacity-100 flex-shrink-0"
                          onClick={() => handleCopyCard(card)}
                          title="Copy card"
                        >
                          {copiedId === card.id ? <Check className="w-3.5 h-3.5 text-success" /> : <Copy className="w-3.5 h-3.5" />}
                        </Button>
                      </div>

                      {/* Summary */}
                      <p className="text-xs text-muted-foreground mb-3 leading-relaxed bg-white/5 p-2.5 rounded-xl border border-white/5">
                        {card.summary}
                      </p>

                      {/* Key Points */}
                      <div className="space-y-1.5 mb-4">
                        <ul className="space-y-1">
                          {card.key_points.map((point, idx) => {
                            const boldMatch = point.match(/^\*\*([^*]+)\*\*:\s*(.*)$/)
                            return (
                              <li key={idx} className="text-xs text-foreground/90 flex items-start gap-2 leading-normal">
                                <span className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5 flex-shrink-0" />
                                {boldMatch ? (
                                  <span>
                                    <strong className="text-foreground font-semibold">{boldMatch[1]}: </strong>
                                    <span>{boldMatch[2]}</span>
                                  </span>
                                ) : (
                                  <span>{point}</span>
                                )}
                              </li>
                            )
                          })}
                        </ul>
                      </div>
                    </div>

                    {/* Footer Citation without page numbers */}
                    <div className="pt-3 border-t border-white/10 flex items-center justify-between text-[10px] text-muted-foreground">
                      <span className="flex items-center gap-1 truncate max-w-[95%]" title={card.source}>
                        <FileText className="w-3 h-3 text-primary flex-shrink-0" />
                        <span className="truncate">{card.source}</span>
                      </span>
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
