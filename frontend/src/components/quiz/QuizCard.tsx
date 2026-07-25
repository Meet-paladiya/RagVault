import { useState } from 'react'
import { motion } from 'framer-motion'
import { ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import type { Quiz, QuizResult, MCQQuestion } from '@/types'

interface QuizCardProps {
  quiz: Quiz
  onSubmit: (answers: Record<string, string>) => void
  isSubmitting?: boolean
}

export function QuizCard({ quiz, onSubmit, isSubmitting }: QuizCardProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})

  const question: MCQQuestion = quiz.questions[currentIndex]
  const progress = ((currentIndex + 1) / quiz.questions.length) * 100
  const isLast = currentIndex === quiz.questions.length - 1
  const hasAnswered = !!answers[question.id]

  const handleSelect = (optionId: string) => {
    setAnswers((prev) => ({ ...prev, [question.id]: optionId }))
  }

  const handleNext = () => {
    if (isLast) {
      onSubmit(answers)
    } else {
      setCurrentIndex((i) => i + 1)
    }
  }

  return (
    <motion.div
      key={currentIndex}
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      className="space-y-4"
    >
      {/* Progress */}
      <div>
        <div className="flex justify-between text-[11px] text-muted-foreground mb-1.5">
          <span>Question {currentIndex + 1} of {quiz.questions.length}</span>
          <span>{quiz.topic}</span>
        </div>
        <Progress value={progress} className="h-1.5" />
      </div>

      {/* Question */}
      <div className="glass-card rounded-xl p-4">
        <p className="text-sm font-medium leading-relaxed">{question.question}</p>
      </div>

      {/* Options */}
      <div className="space-y-2">
        {question.options.map((opt) => {
          const selected = answers[question.id] === opt.id
          return (
            <motion.button
              key={opt.id}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              onClick={() => handleSelect(opt.id)}
              className={`w-full text-left px-3.5 py-3 rounded-lg text-xs font-medium transition-all border ${selected
                  ? 'bg-purple-600/20 border-purple-500/60 text-purple-200'
                  : 'glass border-white/10 hover:border-purple-500/30 hover:bg-white/5'
                }`}
            >
              <span className="mr-2 font-bold text-muted-foreground">{opt.id.toUpperCase()}.</span>
              {opt.text}
            </motion.button>
          )
        })}
      </div>

      {/* Next / Submit */}
      <Button
        onClick={handleNext}
        disabled={!hasAnswered || isSubmitting}
        className="w-full btn-gradient text-white border-0"
        size="sm"
      >
        {isLast ? (isSubmitting ? 'Submitting…' : 'Submit Quiz') : 'Next'}
        <ChevronRight className="w-4 h-4 ml-1" />
      </Button>
    </motion.div>
  )
}

interface QuizResultsProps {
  result: QuizResult
  onRecommendations: () => void
  onRetry: () => void
}

export function QuizResults({ result, onRetry }: QuizResultsProps) {
  const pct = Math.round(result.score)
  const circumference = 2 * Math.PI * 40

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-4"
    >
      {/* Score Ring */}
      <div className="flex flex-col items-center py-2">
        <svg width="100" height="100" className="-rotate-90">
          <circle cx="50" cy="50" r="40" fill="none" stroke="hsl(var(--border))" strokeWidth="8" />
          <motion.circle
            cx="50" cy="50" r="40" fill="none"
            stroke={pct >= 80 ? '#22c55e' : pct >= 50 ? '#a855f7' : '#ef4444'}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: circumference - (pct / 100) * circumference }}
            transition={{ duration: 1, ease: 'easeOut' }}
          />
        </svg>
        <div className="-mt-16 text-center">
          <p className="text-2xl font-bold">{pct}%</p>
          <p className="text-[10px] text-muted-foreground">{result.correct_count}/{result.total_questions} correct</p>
        </div>
      </div>

      <p className="text-xs text-center text-muted-foreground">{result.feedback}</p>

      {/* Weak Topics */}
      {result.weak_topics.length > 0 && (
        <div>
          <p className="text-[11px] font-medium text-muted-foreground mb-1.5">Needs review:</p>
          <div className="flex flex-wrap gap-1.5">
            {result.weak_topics.slice(0, 5).map((t, i) => (
              <Badge key={i} className="text-[10px] bg-orange-500/15 text-orange-400 border-orange-500/30">
                {t.length > 40 ? t.slice(0, 40) + '…' : t}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-col gap-2">

        <Button onClick={onRetry} variant="outline" size="sm" className="w-full border-white/15">
          Try Again
        </Button>
      </div>
    </motion.div>
  )
}
