import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Parse backend timestamps, which are currently stored as UTC without an offset. */
export function parseBackendDate(value: string): Date {
  const normalized = value && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(value)
    ? `${value}Z`
    : value
  return new Date(normalized)
}
