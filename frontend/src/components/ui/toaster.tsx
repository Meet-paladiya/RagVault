import { AnimatePresence, motion } from 'framer-motion'
import { X, CheckCircle2, AlertCircle } from 'lucide-react'
import { useToastState } from './use-toast'

export function Toaster() {
  const { toasts, dismiss } = useToastState()

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm pointer-events-none">
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.95 }}
            transition={{ duration: 0.2 }}
            className={`glass-card rounded-xl px-4 py-3 flex items-start gap-3 pointer-events-auto shadow-2xl border ${
              toast.variant === 'destructive'
                ? 'border-red-500/30 bg-red-900/20'
                : 'border-white/10 bg-card/90'
            }`}
          >
            {toast.variant === 'destructive'
              ? <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
              : <CheckCircle2 className="w-4 h-4 text-green-400 flex-shrink-0 mt-0.5" />}
            <div className="flex-1 min-w-0">
              {toast.title && (
                <p className="text-xs font-semibold text-foreground">{toast.title}</p>
              )}
              {toast.description && (
                <p className="text-xs text-muted-foreground mt-0.5">{toast.description}</p>
              )}
            </div>
            <button
              onClick={() => dismiss(toast.id)}
              className="text-muted-foreground hover:text-foreground transition-colors ml-1"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
