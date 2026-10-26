export interface User {
  id: string;
  name: string;
  email: string;
  created_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Chat {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatListResponse {
  chats: Chat[];
}

export interface Citation {
  source: string;
  page: number;
}

export interface Message {
  id: string;
  chat_id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[] | null;
  created_at: string;
}

export interface MessageListResponse {
  messages: Message[];
}

export interface Document {
  id: string;
  chat_id: string;
  filename: string;
  file_type: string;
  upload_time: string;
  total_pages?: number | null;
  total_chunks?: number | null;
  status: 'processing' | 'processed' | 'failed';
}

export interface DocumentListResponse {
  documents: Document[];
}

export interface MCQOption {
  id: string;
  text: string;
}

export interface MCQQuestion {
  id: string;
  question: string;
  options: MCQOption[];
  correct_option_id: string;
  explanation: string;
}

export interface Quiz {
  id: string;
  chat_id: string;
  topic: string;
  score?: number | null;
  total_questions: number;
  weak_topics?: string[] | null;
  questions: MCQQuestion[];
  created_at: string;
}

export interface QuizStreamInitEvent {
  type: 'init';
  quiz_id: string;
  chat_id: string;
  topic: string;
  target_total: number;
  created_at: string;
}

export interface QuizStreamBatchEvent {
  type: 'batch';
  quiz_id: string;
  batch_index: number;
  new_questions: MCQQuestion[];
  total_loaded: number;
  target_total: number;
  is_complete: boolean;
}

export interface QuizStreamDoneEvent {
  type: 'done';
  quiz_id: string;
  total_questions: number;
  is_complete: boolean;
}

export interface QuizStreamErrorEvent {
  type: 'error';
  detail: string;
}

export type QuizStreamEvent =
  | QuizStreamInitEvent
  | QuizStreamBatchEvent
  | QuizStreamDoneEvent
  | QuizStreamErrorEvent;

export interface WrongQuestionDetail {
  question_id: string;
  question: string;
  user_answer: string;
  correct_answer: string;
  explanation: string;
}

export interface QuizResult {
  quiz_id: string;
  score: number;
  total_questions: number;
  correct_count: number;
  weak_topics: string[];
  feedback: string;
  wrong_questions?: WrongQuestionDetail[];
}

export interface RecommendationResponse {
  chat_id: string;
  recommendations: string;
  generated_at: string;
}

export * from './notes'
