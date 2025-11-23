import os
import json
import logging
import time
import google.generativeai as genai
from typing import Dict, Any, Optional
from PIL import Image
import cv2
import io

logger = logging.getLogger(__name__)

class GeminiVisionService:
    def __init__(self, api_key: str, model_name: str = "models/gemini-flash-latest"):
        if not api_key:
            logger.warning("Gemini API Key not provided. AI features will be disabled.")
            self.model = None
            return
            
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        logger.info(f"Gemini Vision Service initialized with model: {model_name}")

    def analyze_frame(self, cv2_frame) -> Optional[Dict[str, Any]]:
        if not self.model or cv2_frame is None:
            return None

        try:
            # Convert CV2 frame (BGR) to PIL Image (RGB)
            rgb_frame = cv2.cvtColor(cv2_frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)

            # System Prompt
            prompt = """
            You are a drone autonomous navigation assistant. Analyze this image for:
            1. Disasters: Fire, Flood, collapsed buildings, or Humans in distress.
            2. Safe Landing Spots: Flat, open areas (at least 2x2m) clear of obstacles near the disaster.

            Output your response in JSON format containing:
            {
                "hazard_detected": boolean,
                "disaster_detected": boolean,
                "human_detected": boolean,
                "safe_spot_detected": boolean,
                "safe_spot_coords": [x, y] (normalized 0-1 coordinates of the center of the safe spot, or null),
                "suggested_heading_adjustment": number (degrees, positive for right, negative for left, 0 for straight),
                "reasoning": string (concise explanation of what you see and your recommendation)
            }
            Do not include markdown formatting like ```json ... ```. Just the raw JSON.
            """

            # Generate content
            response = self.model.generate_content([prompt, pil_image])
            
            # Parse JSON
            text = response.text.strip()
            # Clean up potential markdown fences if Gemini ignores instruction
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            
            result = json.loads(text)
            return result

        except Exception as e:
            logger.error(f"Gemini analysis failed: {e}")
            return None
