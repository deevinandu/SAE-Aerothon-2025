"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Play, Square, Camera, AlertTriangle } from "lucide-react";
import { VideoSource } from "@/types";

interface VideoPlayerProps {
  source: VideoSource;
  isRecording: boolean;
  onFrameCapture: (frameData: string) => void;
  onRecordingToggle: (recording: boolean) => void;
}

export function VideoPlayer({
  source,
  isRecording,
  onFrameCapture,
  onRecordingToggle,
}: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [frameCount, setFrameCount] = useState(0);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const onFrameCaptureRef = useRef(onFrameCapture);

  useEffect(() => {
    onFrameCaptureRef.current = onFrameCapture;
  }, [onFrameCapture]);

  const captureFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;

    if (!video || !canvas) {
      return;
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      return;
    }

    // Set canvas dimensions to match video
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    // Draw current frame
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    // Convert to base64 JPEG
    const frameData = canvas.toDataURL("image/jpeg", 0.8);
    onFrameCaptureRef.current(frameData);
    setFrameCount((prev) => prev + 1);
  }, [onFrameCapture]);

  const startVideoStream = useCallback(async () => {
    try {
      setError(null);
      const video = videoRef.current;
      if (!video) return;

      let stream: MediaStream;

      if (source.type === "Webcam") {
        const deviceId = source.connectionString || "0";
        const constraints = {
          video: {
            deviceId: deviceId !== "0" ? { exact: deviceId } : undefined,
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
        };
        stream = await navigator.mediaDevices.getUserMedia(constraints);
      } else {
        throw new Error(
          `${source.type} sources require server-side implementation`
        );
      }

      video.srcObject = stream;
      streamRef.current = stream;
      await video.play();
      setIsPlaying(true);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to start video stream"
      );
      setIsPlaying(false);
    }
  }, [source]);

  const stopVideoStream = useCallback(() => {
    const video = videoRef.current;
    if (video) {
      video.pause();
      video.srcObject = null;
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => {
        track.stop();
      });
      streamRef.current = null;
    }

    // Clear recording interval
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    setIsPlaying(false);
    setFrameCount(0);
  }, []);

  const togglePlayback = useCallback(() => {
    if (isPlaying) {
      stopVideoStream();
      onRecordingToggle(false); // Stop frame capture
    } else {
      startVideoStream();
      onRecordingToggle(true); // Start frame capture automatically
    }
  }, [isPlaying, startVideoStream, stopVideoStream, onRecordingToggle]);

  const handleRecordingToggle = useCallback(() => {
    const newRecording = !isRecording;
    console.log(
      `🎬 Recording toggle: ${isRecording} -> ${newRecording}, isPlaying: ${isPlaying}`
    );
    onRecordingToggle(newRecording);

    if (newRecording && isPlaying) {
      // Start frame capture interval
      intervalRef.current = setInterval(captureFrame, 200); // 5 FPS
    } else {
      // Stop frame capture
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
  }, [isRecording, isPlaying, captureFrame, onRecordingToggle]);

  // Start frame capture when recording is enabled and video is playing
  useEffect(() => {
    console.log(
      `🔄 Frame capture effect: isRecording=${isRecording}, isPlaying=${isPlaying}`
    );

    if (isRecording && isPlaying) {
      if (!intervalRef.current) {
        console.log("▶️ Starting frame capture interval (5 FPS) via effect");
        intervalRef.current = setInterval(captureFrame, 200); // 5 FPS
      }
    } else {
      if (intervalRef.current) {
        console.log("⏹️ Stopping frame capture interval via effect");
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
  }, [isRecording, isPlaying, captureFrame]);

  useEffect(() => {
    if (!source.isActive && isPlaying) {
      console.log("Stopping regular video because source is inactive");
      stopVideoStream();
      onRecordingToggle(false); // Disable frame capture when source is inactive
    }
    // No auto-start when source becomes active. User must click Start.
  }, [source.isActive, isPlaying, stopVideoStream, onRecordingToggle]);

  useEffect(() => {
    return () => {
      stopVideoStream();
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [stopVideoStream]);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2">
          <Camera className="h-5 w-5" />
          Video Feed - {source.type}
          <button
            onClick={togglePlayback}
            className={`ml-auto px-3 py-1 rounded-md border-2 ${
              isPlaying
                ? "border-red-500 text-red-600"
                : "border-green-500 text-green-600"
            } cursor-pointer`}
          >
            {isPlaying ? "Stop" : "Start"}
          </button>
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pt-0 pb-4">
        <div
          className="relative bg-black rounded-lg border-2 border-green-500 overflow-hidden mb-3"
          style={{ aspectRatio: "16/9", minHeight: "240px" }}
        >
          {error ? (
            <div className="flex items-center justify-center h-full text-red-400">
              <div className="text-center">
                <AlertTriangle className="h-12 w-12 mx-auto mb-2" />
                <p className="text-sm">{error}</p>
              </div>
            </div>
          ) : (
            <>
              <video
                ref={videoRef}
                className="absolute inset-0 w-full h-full object-contain bg-black"
                muted
                playsInline
                autoPlay
              />
              <canvas ref={canvasRef} className="hidden" />
              {!isPlaying && (
                <div className="absolute inset-0 flex items-center justify-center text-gray-400 bg-gray-900/50 z-10">
                  <div className="text-center">
                    <Camera className="h-16 w-16 mx-auto mb-2 opacity-50" />
                    <p>Click play to start video feed</p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Button moved to header */}
      </CardContent>
    </Card>
  );
}
