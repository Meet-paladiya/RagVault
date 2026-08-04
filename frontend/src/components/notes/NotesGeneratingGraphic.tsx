import { motion } from 'framer-motion'
import { Sparkles, FileText, Brain, Layers, CheckCircle2 } from 'lucide-react'
import { useEffect, useState } from 'react'

const STEPS = [
  'Parsing document resources & vector embeddings...',
  'Extracting core concepts, definitions & formulas...',
  'Synthesizing key takeaways and summaries...',
  'Formatting AI Study Note Cards...',
]

export function NotesGeneratingGraphic() {
  const [currentStep, setCurrentStep] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentStep((prev) => (prev + 1) % STEPS.length)
    }, 2800)
    return () => clearInterval(timer)
  }, [])

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

          {/* Orbiting Floating Cards / Icons */}
          <motion.div
            animate={{ y: [-6, 6, -6], x: [-4, 4, -4] }}
            transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
            className="absolute -top-3 -right-4 bg-surface border border-primary/30 backdrop-blur-md p-2 rounded-xl text-primary shadow-md flex items-center gap-1 text-[11px] font-medium"
          >
            <FileText className="w-3.5 h-3.5" /> Chunks
          </motion.div>

          <motion.div
            animate={{ y: [6, -6, 6], x: [4, -4, 4] }}
            transition={{ duration: 3.5, repeat: Infinity, ease: 'easeInOut' }}
            className="absolute -bottom-3 -left-4 bg-surface border border-blue-400/30 backdrop-blur-md p-2 rounded-xl text-primary shadow-md flex items-center gap-1 text-[11px] font-medium"
          >
            <Layers className="w-3.5 h-3.5" /> Cards
          </motion.div>
        </div>

        {/* Title */}
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="w-5 h-5 text-primary animate-spin" />
          <h3 className="text-lg font-bold gradient-text">Generating AI Study Notes</h3>
        </div>

        <p className="text-xs text-muted-foreground mb-6 leading-relaxed">
          Synthesizing high-yield study cards from all documents uploaded to this Knowledge Space.
        </p>

        {/* Dynamic Progress Indicator */}
        <div className="w-full bg-white/5 border border-white/10 rounded-xl p-3.5 backdrop-blur-sm space-y-2">
          <div className="flex items-center justify-between text-xs text-primary font-medium">
            <span className="flex items-center gap-2">
              <CheckCircle2 className="w-3.5 h-3.5 text-primary animate-pulse" />
              {STEPS[currentStep]}
            </span>
            <span className="text-[10px] text-muted-foreground">{currentStep + 1} / {STEPS.length}</span>
          </div>

          {/* Animated Progress Bar */}
          <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
            <motion.div
              key={currentStep}
              initial={{ width: '0%' }}
              animate={{ width: '100%' }}
              transition={{ duration: 2.8, ease: 'linear' }}
              className="h-full bg-gradient-to-r from-primary to-blue-500"
            />
          </div>
        </div>
      </div>
    </div>
  )
}
