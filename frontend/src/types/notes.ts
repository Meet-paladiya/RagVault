export interface NoteCard {
  id: string
  topic: string
  summary: string
  key_points: string[]
  source?: string
  page?: number
  tag: 'Concept' | 'Definition' | 'Formula' | 'Takeaway' | 'Summary' | string
}

export interface NotesResponse {
  id: string
  chat_id: string
  title: string
  cards: NoteCard[]
  created_at: string
}
