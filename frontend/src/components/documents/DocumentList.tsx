import { motion, AnimatePresence } from 'framer-motion'
import { FileText, Presentation, Video, Music, Trash2, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { useDocuments, useDeleteDocument } from '@/api/documents'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { useToast } from '@/components/ui/use-toast'
import type { Document } from '@/types'

const fileIcon = (ext: string) => {
  if (ext === '.pdf') return <FileText className="w-4 h-4 text-red-400" />
  if (ext === '.pptx') return <Presentation className="w-4 h-4 text-orange-400" />
  if (['.mp4', '.mkv', '.mov', '.avi', '.webm'].includes(ext)) return <Video className="w-4 h-4 text-blue-400" />
  return <Music className="w-4 h-4 text-green-400" />
}

const StatusBadge = ({ status }: { status: Document['status'] }) => {
  if (status === 'processing') return (
    <Badge className="text-[10px] bg-yellow-500/15 text-yellow-400 border-yellow-500/30 gap-1">
      <Loader2 className="w-2.5 h-2.5 animate-spin" /> Processing
    </Badge>
  )
  if (status === 'processed') return (
    <Badge className="text-[10px] bg-green-500/15 text-green-400 border-green-500/30 gap-1">
      <CheckCircle2 className="w-2.5 h-2.5" /> Ready
    </Badge>
  )
  return (
    <Badge className="text-[10px] bg-red-500/15 text-red-400 border-red-500/30 gap-1">
      <XCircle className="w-2.5 h-2.5" /> Failed
    </Badge>
  )
}

interface DocumentListProps {
  chatId: string
}

export function DocumentList({ chatId }: DocumentListProps) {
  const { data, isLoading } = useDocuments(chatId, {
    refetchInterval: (data) =>
      data?.documents?.some((d) => d.status === 'processing') ? 3000 : false,
  })
  const deleteDoc = useDeleteDocument(chatId)
  const { toast } = useToast()

  const docs = data?.documents ?? []

  if (isLoading) return <div className="py-4 text-xs text-muted-foreground text-center">Loading…</div>

  if (docs.length === 0) return (
    <div className="py-6 text-center">
      <FileText className="w-8 h-8 text-muted-foreground mx-auto mb-2 opacity-50" />
      <p className="text-xs text-muted-foreground">No documents yet</p>
      <p className="text-[10px] text-muted-foreground/60 mt-0.5">Upload files below to get started</p>
    </div>
  )

  const handleDelete = async (docId: string, filename: string) => {
    try {
      await deleteDoc.mutateAsync(docId)
      toast({ description: `${filename} removed.` })
    } catch {
      toast({ title: 'Error', description: 'Failed to delete document.', variant: 'destructive' })
    }
  }

  return (
    <div className="space-y-1.5">
      <AnimatePresence>
        {docs.map((doc) => (
          <motion.div
            key={doc.id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -8 }}
            className="group flex items-start gap-2.5 p-2.5 rounded-lg glass hover:bg-white/8 transition-colors"
          >
            <div className="mt-0.5">{fileIcon(doc.file_type)}</div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium truncate text-foreground">{doc.filename}</p>
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                <StatusBadge status={doc.status} />
                {doc.total_chunks != null && (
                  <span className="text-[10px] text-muted-foreground">{doc.total_chunks} chunks</span>
                )}
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="w-6 h-6 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-all"
              onClick={() => handleDelete(doc.id, doc.filename)}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
