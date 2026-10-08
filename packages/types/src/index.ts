export type Rarity = "common" | "uncommon" | "rare" | "epic" | "legendary";
export type VerificationMethod = "self_reported" | "ai_review" | "server_validated" | "human_review";
export type QuestStatus = "draft" | "available" | "active" | "completed" | "failed" | "abandoned";
export type Archetype = "explorer" | "observer" | "seeker" | "wanderer";
export type QuestCategory = "exploration" | "observation" | "discovery" | "mystery" | "photography" | "challenge" | "chaos" | "story";
export type EnvironmentType = "unknown" | "indoor" | "urban" | "nature" | "home";
export type WeatherType = "unknown" | "clear" | "rain" | "snow" | "hot" | "cold";
export type DayPeriod = "unknown" | "morning" | "afternoon" | "evening" | "night";

export interface PlayerStats {
  str: number;
  agi: number;
  int: number;
  vit: number;
  lck: number;
}
export interface PlayerPreferences {
  interests: string;
  quest_duration_minutes: number;
}

export interface APIError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string;
}
export interface APIResponse<T> {
  data: T | null;
  error: APIError | null;
  meta: Record<string, unknown>;
}
export interface Player {
  id: string;
  display_name: string;
  created_at: string;
  archetype: Archetype;
  level: number;
  experience: number;
  experience_to_next_level: number;
  aether: number;
  stats: PlayerStats;
  preferences: PlayerPreferences;
  progress?: Progress | null;
}
export interface Objective {
  id: string;
  description: string;
  optional: boolean;
  verification: VerificationMethod;
}
export interface Reward {
  id: string;
  kind: string;
  quantity: number;
  rarity: Rarity;
  description?: string | null;
}
export interface Quest {
  id: string;
  player_id: string;
  title: string;
  description: string;
  category: QuestCategory;
  difficulty: number;
  estimated_minutes: number;
  objectives: Objective[];
  verification: VerificationMethod[];
  xp_reward: number;
  aether_reward: number;
  status: QuestStatus;
  level: number;
  created_at: string;
}
export interface QuestAttempt {
  id: string;
  player_id: string;
  quest_id: string;
  status: QuestStatus;
  started_at: string;
  completed_at?: string | null;
  objective_progress: Record<string, boolean>;
}
export interface InventoryItem { id: string; item_id: string; quantity: number; rarity: Rarity }
export interface Summon { id: string; player_id: string; entity_id: string; acquired_at: string; rarity: Rarity }
export interface Discovery { id: string; player_id: string; subject_id: string; discovered_at: string }
export interface Progress { level: number; experience: number; completed_quest_ids: string[] }
export interface NPC { id: string; name: string; description: string; location_id?: string | null }
export interface WorldEvent { id: string; title: string; description: string; starts_at: string; ends_at?: string | null }
