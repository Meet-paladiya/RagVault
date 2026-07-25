import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion } from 'framer-motion'
import { UploadCloud, FileText, Presentation, Video, Music } from 'lucide-react'
import { useUploadDocument } from '@/api/documents'
import { useToast } from '@/components/ui/use-toast'

const ACCEPTED_TYPES: Record<string, string[]> = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
  'video/mp4': ['.mp4'], 'video/x-matroska': ['.mkv'], 'video/quicktime': ['.mov'],
  'video/x-msvideo': ['.avi'], 'video/webm': ['.webm'],
  'audio/mpeg': ['.mp3'], 'audio/wav': ['.wav'], 'audio/mp4': ['.m4a'],
  'audio/ogg': ['.ogg'], 'audio/flac': ['.flac'], 'audio/aac': ['.aac'],
}

const FILE_LABELS = [
  { icon: FileText, label: 'PDF', color: 'text-red-400' },
  { icon: Presentation, label: 'PPTX', color: 'text-orange-400' },
  { icon: Video, label: 'Video', color: 'text-blue-400' },
  { icon: Music, label: 'Audio', color: 'text-green-400' },
]

interface DropZoneProps {
  chatId: string
}

export function DropZone({ chatId }: DropZoneProps) {
  const upload = useUploadDocument(chatId)
  const { toast } = useToast()

  const onDrop = useCallback(
    async (acceptedFiles: File[], rejectedFiles: any[]) => {
      if (rejectedFiles.length > 0) {
        const names = rejectedFiles.map((r) => r.file.name).join(', ')
        toast({
          title: 'Unsupported file type',
          description: `${names} — only PDF, PPTX, video, and audio files are accepted.`,
          variant: 'destructive',
        })
      }
      for (const file of acceptedFiles) {
        try {
          await upload.mutateAsync(file)
          toast({ title: 'Uploading', description: `${file.name} is being processed…` })
        } catch {
          toast({ title: 'Upload failed', description: `Failed to upload ${file.name}.`, variant: 'destructive' })
        }
      }
    },
    [upload, toast]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    maxSize: 2 * 1024 * 1024 * 1024,
  })

  return (
    <motion.div
      {...(getRootProps() as any)}
      whileHover={{ scale: 1.01 }}
      className={`border-2 border-dashed rounded-xl p-3 cursor-pointer transition-colors duration-200 ${
        isDragActive
          ? 'border-purple-500 bg-purple-500/10 animate-glow'
          : 'border-white/15 hover:border-purple-500/50 hover:bg-white/3'
      }`}
    >
      <input {...getInputProps()} />
      <div className="flex flex-col items-center gap-1 text-center">
        <motion.div
          animate={isDragActive ? { scale: [1, 1.15, 1], rotate: [0, -5, 5, 0] } : {}}
          transition={{ repeat: isDragActive ? Infinity : 0, duration: 0.6 }}
        >
          <UploadCloud className={`w-6 h-6 ${isDragActive ? 'text-purple-400' : 'text-muted-foreground'}`} />
        </motion.div>
        <p className="text-xs font-medium text-foreground">
          {isDragActive ? 'Drop to upload' : 'Drag & drop files'}
        </p>
        <p className="text-[10px] text-muted-foreground">or click to browse</p>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap justify-center">
          {FILE_LABELS.map(({ icon: Icon, label, color }) => (
            <div key={label} className="flex items-center gap-0.5">
              <Icon className={`w-2.5 h-2.5 ${color}`} />
              <span className="text-[9px] text-muted-foreground">{label}</span>
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  )
}
