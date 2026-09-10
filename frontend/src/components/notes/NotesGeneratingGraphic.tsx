import { motion } from 'framer-motion'
import { Sparkles, FileText, Brain } from 'lucide-react'

export function NotesGeneratingGraphic() {
  return (
    <div className="flex flex-col items-center justify-center h-full w-full p-8 text-center glass-card rounded-2xl relative overflow-hidden">
      {/* Background Animated Glow Spheres */}
      <motion.div
        animate={{ scale: [1, 1.25, 1], opacity: [0.3, 0.6, 0.3] }}
        transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute w-72 h-72 rounded-full bg-primary/15 blur-3xl pointer-events-none"
      />
      <motion.div
        animate={{ scale: [1.2, 1, 1.2], opacity: [0.2, 0.5, 0.2] }}
        transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
        className="absolute w-60 h-60 rounded-full bg-blue-500/15 blur-3xl pointer-events-none"
      />

      {/* Main Central Graphics Container */}
      <div className="relative z-10 flex flex-col items-center max-w-md">
        <div className="relative mb-8 flex items-center justify-center">
          {/* Outer Rotating Scanning Ring */}
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 10, repeat: Infinity, ease: 'linear' }}
            className="w-32 h-32 rounded-full border-2 border-dashed border-primary/40 p-2 flex items-center justify-center"
          />

          {/* Pulsing Core */}
          <motion.div
            animate={{ scale: [0.95, 1.08, 0.95] }}
            transition={{ duration: 2, repeat: Infinity, ease: 'easeInOut' }}
            className="absolute w-24 h-24 rounded-2xl bg-gradient-to-br from-primary to-blue-600 flex items-center justify-center shadow-lg shadow-primary/30 border border-white/20"
          >
            <Brain className="w-12 h-12 text-white animate-pulse" />
          </motion.div>

          <motion.div
            animate={{ y: [-6, 6, -6], x: [-4, 4, -4] }}
            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
            className="absolute -top-3 -right-4 bg-surface border border-primary/30 backdrop-blur-md p-2 rounded-xl text-primary shadow-md flex items-center gap-1 text-[11px] font-medium"
          >
            <FileText className="w-3.5 h-3.5" /> Reading pages
          </motion.div>

          <motion.div
            animate={{ y: [6, -6, 6], x: [4, -4, 4] }}
            transition={{ duration: 3.5, repeat: Infinity, ease: 'easeInOut' }}
            className="absolute -bottom-3 -left-4 bg-surface border border-blue-400/30 backdrop-blur-md p-2 rounded-xl text-primary shadow-md flex items-center gap-1 text-[11px] font-medium"
          >
            <FileText className="w-3.5 h-3.5" /> Building PDF
          </motion.div>
        </div>

        {/* Title */}
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="w-5 h-5 text-primary animate-spin" />
          <h3 className="text-lg font-bold gradient-text">Generating AI Study Notes</h3>
        </div>

        <p className="text-xs text-muted-foreground mb-6 leading-relaxed">
          Creating a complete page-by-page study summary with formulas and important details. This can take a while on a CPU-only laptop.
        </p>

        <div className="w-full bg-white/5 border border-white/10 rounded-xl p-3.5 backdrop-blur-sm space-y-2">
          <div className="flex items-center gap-2 text-xs text-primary font-medium">
            <Sparkles className="w-3.5 h-3.5 text-primary animate-pulse" />
            Generating exam-ready notes...
          </div>
          <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
            <motion.div
              animate={{ x: ['-100%', '100%'] }}
              transition={{ duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
              className="h-full w-1/3 bg-gradient-to-r from-primary to-blue-500"
            />
          </div>
        </div>
      </div>
    </div>
  )
}
