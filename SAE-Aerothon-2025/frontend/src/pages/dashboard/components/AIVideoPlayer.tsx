"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Brain, AlertTriangle } from "lucide-react";
import { AnalysisResult } from "@/types";

interface AIVideoPlayerProps {
  sessionId: string;
  onFrameAnalysis: (result: AnalysisResult) => void;
  backendUrl: string;
  frameDataUrl: string | null; // Receive frame from parent
  shouldAnalyze: boolean; // Control when to analyze
  isAnalysisEnabled: boolean;
  onToggleAnalysis: () => void;
  frameNumber: number;
}

interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
  confidence: number;
  label: string;
}

export function AIVideoPlayer({
  sessionId,
  onFrameAnalysis,
  backendUrl,
  frameDataUrl,
  shouldAnalyze,
  isAnalysisEnabled,
  onToggleAnalysis,
  frameNumber,
}: AIVideoPlayerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);

  const [error, setError] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [lastAnalysis, setLastAnalysis] = useState<AnalysisResult | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [detectedObjects, setDetectedObjects] = useState<BoundingBox[]>([]);
  const [displayFrame, setDisplayFrame] = useState<string | null>(null);

  // Draw bounding boxes on the overlay canvas
  const drawBoundingBoxes = useCallback(
    (boxes: BoundingBox[], imageWidth: number, imageHeight: number) => {
      const overlayCanvas = overlayCanvasRef.current;
      if (!overlayCanvas) return;

      const ctx = overlayCanvas.getContext("2d");
      if (!ctx) return;

      // Set canvas size to match the image
      overlayCanvas.width = imageWidth;
      overlayCanvas.height = imageHeight;

      // Clear previous drawings
      ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

      // Set up drawing style
      ctx.lineWidth = 3;
      ctx.font = "16px Arial";
      ctx.textBaseline = "top";

      boxes.forEach((box, index) => {
        // Color based on confidence
        const alpha = Math.max(0.6, box.confidence);
        const hue = (index * 137.508) % 360;
        ctx.strokeStyle = `hsla(${hue}, 70%, 50%, ${alpha})`;
        ctx.fillStyle = `hsla(${hue}, 70%, 50%, 0.2)`;

        // Draw bounding box
        ctx.fillRect(box.x, box.y, box.width, box.height);
        ctx.strokeRect(box.x, box.y, box.width, box.height);

        // Draw label background
        const labelText = `${box.label} (${(box.confidence * 100).toFixed(
          1
        )}%)`;
        const textMetrics = ctx.measureText(labelText);
        const labelHeight = 20;

        ctx.fillStyle = `hsla(${hue}, 70%, 40%, 0.8)`;
        ctx.fillRect(
          box.x,
          Math.max(0, box.y - labelHeight),
          textMetrics.width + 8,
          labelHeight
        );

        // Draw label text
        ctx.fillStyle = "white";
        ctx.fillText(
          labelText,
          box.x + 4,
          Math.max(0, box.y - labelHeight) + 2
        );
      });
    },
    []
  );

  // Parse analysis results to extract bounding boxes with normalized coordinates
  const parseAnalysisForBoundingBoxes = useCallback(
    (
      analysis: AnalysisResult,
      imageWidth: number,
      imageHeight: number
    ): BoundingBox[] => {
      const boxes: BoundingBox[] = [];

      // Extract objects from analysis
      if (analysis.objects && analysis.objects.length > 0) {
        analysis.objects.forEach((obj) => {
          if (obj.bbox && Array.isArray(obj.bbox) && obj.bbox.length === 4) {
            // Backend returns normalized 0-1000 coordinates in format [ymin, xmin, ymax, xmax]
            const [ymin, xmin, ymax, xmax] = obj.bbox;

            // Convert to pixel coordinates
            const x = (xmin / 1000) * imageWidth;
            const y = (ymin / 1000) * imageHeight;
            const width = ((xmax - xmin) / 1000) * imageWidth;
            const height = ((ymax - ymin) / 1000) * imageHeight;

            boxes.push({
              x,
              y,
              width,
              height,
              confidence: obj.confidence || 0.8,
              label: obj.label,
            });
          }
        });
      }

      // Fallback: use general bboxes if objects don't have individual bboxes
      if (boxes.length === 0 && analysis.bboxes && analysis.bboxes.length > 0) {
        analysis.bboxes.forEach((bbox, index) => {
          if (Array.isArray(bbox) && bbox.length === 4) {
            const [ymin, xmin, ymax, xmax] = bbox;

            const x = (xmin / 1000) * imageWidth;
            const y = (ymin / 1000) * imageHeight;
            const width = ((xmax - xmin) / 1000) * imageWidth;
            const height = ((ymax - ymin) / 1000) * imageHeight;

            boxes.push({
              x,
              y,
              width,
              height,
              confidence: 0.8,
              label: analysis.labels[index] || `Object ${index + 1}`,
            });
          }
        });
      }

      return boxes;
    },
    []
  );

  // Analyze frame when parent triggers it and analysis is enabled
  useEffect(() => {
    if (!isAnalysisEnabled) return;
    if (!shouldAnalyze || !frameDataUrl || isAnalyzing) return;

    console.log("🚀 Starting AI frame analysis...");
    const analyzeFrame = async () => {
      setIsAnalyzing(true);
      setError(null);
      const startTime = Date.now();

      try {
        // Convert data URL to blob
        const response = await fetch(frameDataUrl);
        const blob = await response.blob();

        // Send to backend (contextual)
        const formData = new FormData();
        formData.append("file", blob, "frame.jpg");
        formData.append("session_id", sessionId);
        formData.append("frame_number", String(frameNumber));
        formData.append("is_first_frame", String(frameNumber === 0));

        const apiResponse = await fetch(
          `${backendUrl}/analyze_frame_contextual`,
          {
            method: "POST",
            body: formData,
          }
        );

        if (apiResponse.ok) {
          const result = await apiResponse.json();
          console.log("🔍 Backend result:", result);
          console.log("📦 Objects array:", result.objects);
          console.log("📊 Bboxes array:", result.bboxes);
          const endTime = Date.now();
          const latencyMs = endTime - startTime;

          setLatency(latencyMs);
          setLastAnalysis(result);
          setDisplayFrame(frameDataUrl);

          // Load image to get dimensions
          const img = new Image();
          img.onload = () => {
            const boxes = parseAnalysisForBoundingBoxes(
              result,
              img.width,
              img.height
            );
            console.log("🎯 Parsed boxes:", boxes);
            setDetectedObjects(boxes);
            drawBoundingBoxes(boxes, img.width, img.height);
            onFrameAnalysis(result);
          };
          img.src = frameDataUrl;
        } else {
          setError(`Backend error: ${apiResponse.statusText}`);
        }
      } catch (error) {
        console.error("Analysis error:", error);
        setError("Backend connection failed");
      } finally {
        setIsAnalyzing(false);
      }
    };

    analyzeFrame();
  }, [
    isAnalysisEnabled,
    shouldAnalyze,
    frameDataUrl,
    sessionId,
    backendUrl,
    isAnalyzing,
    parseAnalysisForBoundingBoxes,
    drawBoundingBoxes,
    onFrameAnalysis,
  ]);

  return (
    <Card className="w-full">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5" />
          AI Object Detection
          <button
            onClick={onToggleAnalysis}
            className={`ml-auto px-3 py-1 rounded-md border-2 ${
              isAnalysisEnabled
                ? "border-red-500 text-red-600"
                : "border-green-500 text-green-600"
            } cursor-pointer`}
          >
            {isAnalysisEnabled ? "Stop Analysis" : "Start Analysis"}
          </button>
          {isAnalyzing && (
            <Badge variant="default" className="ml-auto animate-pulse">
              Analyzing...
            </Badge>
          )}
        </CardTitle>
      </CardHeader>

      <CardContent className="px-4 pt-0 pb-4">
        <div
          className="relative bg-black rounded-lg border-2 border-blue-500 w-full overflow-hidden mb-3"
          style={{ aspectRatio: "16/9", minHeight: "240px" }}
        >
          {displayFrame ? (
            <div className="relative w-full h-full">
              <img
                ref={imageRef}
                src={displayFrame}
                alt="Analyzed frame"
                className="absolute inset-0 w-full h-full object-contain"
              />
              <canvas
                ref={overlayCanvasRef}
                className="absolute inset-0 w-full h-full object-contain pointer-events-none"
                style={{ zIndex: 10 }}
              />
            </div>
          ) : (
            <div className="absolute inset-0 flex items-center justify-center text-gray-400">
              <div className="text-center">
                <Brain className="h-12 w-12 mx-auto mb-2 opacity-50" />
                <p>Waiting for analysis...</p>
              </div>
            </div>
          )}

          {error && (
            <div className="absolute inset-0 flex items-center justify-center bg-black bg-opacity-75">
              <div className="text-center text-white p-4">
                <AlertTriangle className="h-8 w-8 mx-auto mb-2 text-yellow-500" />
                <p className="text-sm">{error}</p>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
