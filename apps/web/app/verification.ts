import type { GeoPoint, VerificationLevel, VerificationResult } from "@realm/types";

export interface VerificationService { verify(input: Record<string, unknown>): Promise<VerificationResult> }

export function calculateDistance(pointA: GeoPoint, pointB: GeoPoint): number {
  const radians = (degrees: number) => degrees * Math.PI / 180;
  const lat1 = radians(pointA.latitude), lat2 = radians(pointB.latitude);
  const dLat = lat2 - lat1, dLon = radians(pointB.longitude - pointA.longitude);
  const value = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 6_371_000 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
}

export class SelfVerification implements VerificationService {
  async verify(input: Record<string, unknown>): Promise<VerificationResult> {
    return { verified: input.confirmed === true, method: "self", message: input.confirmed === true ? "Objective marked complete." : "Completion was not confirmed." };
  }
}

export class LocationVerification implements VerificationService {
  async verify(input: Record<string, unknown>): Promise<VerificationResult> {
    if (!navigator.geolocation) return { verified: false, method: "location", message: "Location is unavailable in this browser." };
    try {
      const point = await new Promise<GeoPoint>((resolve, reject) => navigator.geolocation.getCurrentPosition(
        ({ coords }) => resolve({ latitude: coords.latitude, longitude: coords.longitude }), reject,
        { enableHighAccuracy: false, timeout: 12_000, maximumAge: 30_000 },
      ));
      const target = input.target as GeoPoint | undefined;
      const origin = input.origin as GeoPoint | undefined;
      const radius = typeof input.radiusMeters === "number" ? input.radiusMeters : 100;
      const minimum = typeof input.minimumDistanceMeters === "number" ? input.minimumDistanceMeters : 0;
      const passed = !target || (calculateDistance(point, target) <= radius && (!origin || calculateDistance(origin, point) >= minimum));
      return { verified: passed, method: "location", message: passed ? "Location requirement verified." : "The location requirement was not met." };
    } catch { return { verified: false, method: "location", message: "Location permission was denied or the position could not be read." }; }
  }
}

export class VisionVerification implements VerificationService {
  async verify(input: Record<string, unknown>): Promise<VerificationResult> {
    const file = input.file;
    const api = input.api as (image: string, objective: string) => Promise<VerificationResult> | undefined;
    if (!(file instanceof File) || !api) return { verified: false, method: "vision", message: "Choose an image to review." };
    if (!file.type.startsWith("image/") || file.size > 8 * 1024 * 1024) return { verified: false, method: "vision", message: "Choose an image smaller than 8 MB." };
    const image = await new Promise<string>((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",")[1] ?? ""); reader.onerror = reject; reader.readAsDataURL(file); });
    return await api(image, String(input.objective ?? "")) ?? { verified: false, method: "vision", message: "Vision review is unavailable." };
  }
}

export class CombinedVerification implements VerificationService {
  async verify(input: Record<string, unknown>): Promise<VerificationResult> {
    const location = await new LocationVerification().verify(input);
    if (!location.verified) return { ...location, method: "combined" as VerificationLevel };
    return { ...await new VisionVerification().verify(input), method: "combined" };
  }
}
