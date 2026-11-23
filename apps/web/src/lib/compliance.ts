import type { RecommendationGateState } from "./types";

export function consultationCanComplete(suitabilityChecked: boolean, explanationChecked: boolean): boolean {
  return suitabilityChecked && explanationChecked;
}

export function allRecommendationGatesPass(value: RecommendationGateState): boolean {
  return Object.values(value).every(Boolean);
}
