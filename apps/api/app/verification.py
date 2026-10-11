"""Verification primitives. Location samples are evaluated in memory and never persisted."""
from __future__ import annotations

import base64
import json
import math
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .config import settings


def calculate_distance(point_a: dict[str, float], point_b: dict[str, float]) -> float:
    """Great-circle distance in meters between {latitude, longitude} points."""
    radius = 6_371_000
    lat1, lat2 = math.radians(point_a["latitude"]), math.radians(point_b["latitude"])
    dlat = lat2 - lat1
    dlon = math.radians(point_b["longitude"] - point_a["longitude"])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    value = min(1.0, max(0.0, value))
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


class VerificationService(ABC):
    method: str

    @abstractmethod
    async def verify(self, **evidence: Any) -> dict[str, Any]: ...


class SelfVerification(VerificationService):
    method = "self"

    async def verify(self, **evidence: Any) -> dict[str, Any]:
        return {"verified": bool(evidence.get("confirmed")), "method": self.method,
                "message": "Objective marked complete." if evidence.get("confirmed") else "Completion was not confirmed."}


class LocationVerification(VerificationService):
    method = "location"

    async def verify(self, **evidence: Any) -> dict[str, Any]:
        point = evidence.get("point")
        target = evidence.get("target")
        radius = max(1, float(evidence.get("radius_meters", 100)))
        minimum = max(0, float(evidence.get("minimum_distance_meters", 0)))
        if not point or not target:
            return {"verified": False, "method": self.method, "message": "Location and target are required."}
        distance = calculate_distance(point, target)
        passed = distance <= radius and (not evidence.get("origin") or calculate_distance(evidence["origin"], point) >= minimum)
        return {"verified": passed, "method": self.method,
                "message": "Area reached." if passed else "The location requirement was not met."}


class VisionVerification(VerificationService):
    method = "vision"

    async def verify(self, **evidence: Any) -> dict[str, Any]:
        image = evidence.get("image_base64", "")
        instruction = str(evidence.get("objective", ""))[:500]
        try:
            raw = base64.b64decode(image, validate=True)
        except (ValueError, TypeError):
            return {"verified": False, "method": self.method, "message": "Choose a valid image first."}
        if not raw or len(raw) > 8 * 1024 * 1024:
            return {"verified": False, "method": self.method, "message": "Image must be smaller than 8 MB."}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=5)) as client:
                response = await client.post(f"{settings.ollama_base_url.rstrip('/')}/api/chat", json={
                    "model": settings.vision_model or settings.ollama_model,
                    "stream": False,
                    "format": {"type": "object", "properties": {"verified": {"type": "boolean"}, "confidence": {"type": "number"}, "reason": {"type": "string"}}, "required": ["verified", "confidence", "reason"]},
                    "messages": [{"role": "user", "content": f"Check only whether this image provides reasonable visual evidence for this safe objective: {instruction}. Do not infer location, identity, time, or events outside the image. Return verified false if uncertain, confidence 0..1, concise reason.", "images": [base64.b64encode(raw).decode("ascii")]}],
                })
                response.raise_for_status()
                result = json.loads(response.json()["message"]["content"])
                confidence = min(1, max(0, float(result.get("confidence", 0))))
                passed = bool(result.get("verified")) and confidence >= 0.7
                return {"verified": passed, "method": self.method, "confidence": confidence,
                        "message": str(result.get("reason", "Image reviewed."))[:300]}
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            return {"verified": False, "method": self.method, "message": "Vision review is unavailable right now."}


class CombinedVerification(VerificationService):
    method = "combined"

    async def verify(self, **evidence: Any) -> dict[str, Any]:
        location = await LocationVerification().verify(**evidence)
        if not location["verified"]:
            return {"verified": False, "method": self.method, "message": "Location requirement was not met."}
        vision = await VisionVerification().verify(**evidence)
        return {**vision, "method": self.method, "verified": bool(vision["verified"]),
                "message": "Location and image verified." if vision["verified"] else vision["message"]}
