import { useState, useCallback } from 'react'

interface ToastOptions {
  title?: string
  description?: string
  variant?: 'default' | 'destructive'
  duration?: number
}

interface Toast extends ToastOptions {
  id: string
}

let globalToastFn: ((opts: ToastOptions) => void) | null = null

export function useToast() {
  return {
    toast: (opts: ToastOptions) => {
      if (globalToastFn) globalToastFn(opts)
    },
  }
}

export function useToastState() {
  const [toasts, setToasts] = useState<Toast[]>([])

  const toast = useCallback((opts: ToastOptions) => {
    const id = Math.random().toString(36).slice(2)
    const newToast: Toast = { id, duration: 4000, ...opts }
    setToasts((prev) => [...prev, newToast])
    globalToastFn = (o) => {
      const tid = Math.random().toString(36).slice(2)
      setToasts((prev) => [...prev, { id: tid, duration: 4000, ...o }])
    }
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, newToast.duration)
  }, [])

  // Register global
  globalToastFn = toast

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return { toasts, toast, dismiss }
}
