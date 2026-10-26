import { useState } from 'react'
import { motion } from 'framer-motion'
import { ChevronRight, XCircle, CheckCircle2, BookOpen, RotateCcw, Sparkles, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import type { Quiz, QuizResult, MCQQuestion } from '@/types'

interface QuizCardProps {
  quiz: Quiz
  onSubmit: (answers: Record<string, string>) => void
  isSubmitting?: boolean
  isLoadingMore?: boolean
  targetTotal?: number
}

export function QuizCard({ quiz, onSubmit, isSubmitting, isLoadingMore = false, targetTotal }: QuizCardProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [answers, setAnswers] = useState<Record<string, string>>({})

  const totalTarget = targetTotal || quiz.total_questions || quiz.questions.length || 20
  const question: MCQQuestion | undefined = quiz.questions[currentIndex]
  const isLoadedLast = currentIndex >= quiz.questions.length - 1
  const isTrueLast = isLoadedLast && !isLoadingMore && quiz.questions.length >= totalTarget
  const isWaitingForMore = isLoadedLast && isLoadingMore && quiz.questions.length < totalTarget
  const progress = Math.min(100, ((currentIndex + 1) / totalTarget) * 100)
  const hasAnswered = question ? !!answers[question.id] : false

  const handleSelect = (optionId: string) => {
    if (!question) return
    setAnswers((prev) => ({ ...prev, [question.id]: optionId }))
  }

  const handleNext = () => {
    if (isTrueLast) {
      onSubmit(answers)
    } else if (!isLoadedLast) {
      setCurrentIndex((i) => i + 1)
    }
  }

  if (!question) {
    return (
      <div className="glass-card rounded-xl p-8 text-center space-y-3">
        <Loader2 className="w-6 h-6 animate-spin mx-auto text-purple-400" />
        <p className="text-xs font-medium text-foreground">Preparing first batch of questions…</p>
        <p className="text-[11px] text-muted-foreground">The first 2–3 questions will appear in a few seconds.</p>
      </div>
    )
  }

  return (
    <motion.div
      key={currentIndex}
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      className="space-y-4"
    >
      {/* Progress & Live Generation Badge */}
      <div>
        <div className="flex items-center justify-between text-[11px] text-muted-foreground mb-1.5">
          <span className="font-semibold text-foreground">
            Question {currentIndex + 1} of {totalTarget}
          </span>
          {isLoadingMore ? (
            <span className="flex items-center gap-1.5 text-[10px] text-purple-300 bg-purple-500/15 border border-purple-500/25 px-2 py-0.5 rounded-full animate-pulse font-medium">
              <Loader2 className="w-2.5 h-2.5 animate-spin text-purple-400" />
              <span>Generating in background ({quiz.questions.length}/{totalTarget} ready)</span>
            </span>
          ) : (
            <span className="flex items-center gap-1 text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full font-medium">
              <Sparkles className="w-2.5 h-2.5 text-emerald-400" />
              <span>All {quiz.questions.length} questions ready</span>
            </span>
          )}
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
                  ? 'bg-primary/20 border-primary/60 text-foreground'
                  : 'glass border-white/10 hover:border-primary/30 hover:bg-white/5'
                }`}
            >
              <span className="mr-2 font-bold text-muted-foreground">{opt.id.toUpperCase()}.</span>
              {opt.text}
            </motion.button>
          )
        })}
      </div>

      {/* Next / Waiting / Submit */}
      {isWaitingForMore ? (
        <div className="space-y-2 pt-1">
          <Button
            disabled
            className="w-full bg-white/5 text-muted-foreground border border-white/10 h-9 text-xs"
            size="sm"
          >
            <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5 text-purple-400" />
            Preparing next questions… ({quiz.questions.length}/{totalTarget} loaded)
          </Button>
          {hasAnswered && (
            <div className="text-center">
              <button
                type="button"
                onClick={() => onSubmit(answers)}
                disabled={isSubmitting}
                className="text-[11px] text-muted-foreground hover:text-foreground transition-colors underline underline-offset-2"
              >
                Or submit quiz now ({quiz.questions.length} questions completed)
              </button>
            </div>
          )}
        </div>
      ) : (
        <Button
          onClick={handleNext}
          disabled={!hasAnswered || isSubmitting}
          className="w-full btn-gradient text-white border-0"
          size="sm"
        >
          {isTrueLast ? (isSubmitting ? 'Submitting…' : 'Submit Quiz') : 'Next'}
          <ChevronRight className="w-4 h-4 ml-1" />
        </Button>
      )}
    </motion.div>
  )
}

interface QuizResultsProps {
  result: QuizResult
  onRecommendations?: () => void
  onRetry: () => void
  onGenerateRemedialNotes?: () => void
  isGeneratingRemedial?: boolean
}

export function QuizResults({ result, onRetry, onGenerateRemedialNotes, isGeneratingRemedial }: QuizResultsProps) {
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
            stroke={pct >= 80 ? '#22c55e' : pct >= 50 ? '#3b82f6' : '#ef4444'}
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
      {result.weak_topics && result.weak_topics.length > 0 && (
        <div>
          <p className="text-[11px] font-medium text-muted-foreground mb-1.5">Needs review:</p>
          <div className="flex flex-wrap gap-1.5">
            {result.weak_topics.slice(0, 5).map((t, i) => (
              <Badge key={i} className="text-[10px] bg-warning/15 text-warning border-warning/30">
                {t.length > 40 ? t.slice(0, 40) + '…' : t}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {/* Incorrect Questions & Paragraph Explanations */}
      {result.wrong_questions && result.wrong_questions.length > 0 && (
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between border-b border-white/10 pb-2">
            <h4 className="text-xs font-bold flex items-center gap-1.5 text-foreground">
              <XCircle className="w-4 h-4 text-red-400" />
              Incorrect Questions ({result.wrong_questions.length})
            </h4>
          </div>

          <div className="space-y-3 max-h-[380px] overflow-y-auto pr-1">
            {result.wrong_questions.map((item, index) => (
              <div
                key={item.question_id || index}
                className="glass-card rounded-xl p-3.5 border border-white/10 space-y-2.5 shadow-sm"
              >
                <p className="text-xs font-semibold text-foreground leading-snug">
                  {index + 1}. {item.question}
                </p>

                <div className="grid grid-cols-1 gap-1.5 text-[11px]">
                  <div className="flex items-start gap-1.5 p-2 rounded-lg bg-red-500/10 border border-red-500/20 text-red-300">
                    <XCircle className="w-3.5 h-3.5 text-red-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <span className="font-medium opacity-80">Your Answer: </span>
                      <span>{item.user_answer}</span>
                    </div>
                  </div>

                  <div className="flex items-start gap-1.5 p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-300">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 mt-0.5" />
                    <div>
                      <span className="font-medium opacity-80">Correct Answer: </span>
                      <span className="font-semibold">{item.correct_answer}</span>
                    </div>
                  </div>
                </div>

                {/* Paragraph Explanation */}
                <div className="p-3 rounded-lg bg-white/5 border border-white/10 text-xs leading-relaxed space-y-1">
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold text-primary">
                    <BookOpen className="w-3.5 h-3.5 text-primary" />
                    <span>Paragraph Explanation:</span>
                  </div>
                  <p className="text-[11px] leading-relaxed text-muted-foreground">
                    {item.explanation}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-col gap-2 pt-2">
        {onGenerateRemedialNotes && (
          <Button
            onClick={onGenerateRemedialNotes}
            disabled={isGeneratingRemedial}
            className="w-full btn-gradient text-white border-0 h-9 text-xs font-semibold rounded-xl"
          >
            <Sparkles className="w-3.5 h-3.5 mr-1.5 text-amber-300" />
            {isGeneratingRemedial ? 'Generating Remedial Notes...' : 'Generate Wrong Answers Notes & PDF'}
          </Button>
        )}
        <Button onClick={onRetry} variant="outline" size="sm" className="w-full border-white/15">
          <RotateCcw className="w-3.5 h-3.5 mr-1.5" /> Try Another Quiz
        </Button>
      </div>
    </motion.div>
  )
}
