import { get, put } from "@/utils/http";
import type { AiProfile } from "./types";

/** 提示词上限，和后端 PROFILE_HINTS_LIMIT 保持一致。 */
export const HINTS_LIMIT = 500;

export function fetchProfile(): Promise<AiProfile> {
  return get<AiProfile>("/v1/ai/profile");
}

export function saveProfile(hints: string): Promise<AiProfile> {
  return put<AiProfile>("/v1/ai/profile", { hints }, { silent: true });
}
