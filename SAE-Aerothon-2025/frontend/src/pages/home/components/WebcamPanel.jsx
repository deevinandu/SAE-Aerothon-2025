"use client";

import React, { useEffect, useRef, useState } from "react";
import { Video, VideoOff, Maximize2, Minimize2 } from "lucide-react";

export default function WebcamPanel({
  isFullscreen = false,
  onToggleFullscreen,
}) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [isActive, setIsActive] = useState(false);
  const [error, setError] = useState("");

  const startWebcam = async () => {
    try {
      setError("");
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: "user",
        },
        audio: false,
      });

      streamRef.current = stream;

      // Set stream immediately since video element is always rendered
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        // Try to play immediately
        videoRef.current.play().catch((err) => {
          console.error("Error playing video immediately:", err);
        });
        // Also try when metadata is loaded
        videoRef.current.onloadedmetadata = () => {
          if (videoRef.current) {
            videoRef.current.play().catch((err) => {
              console.error("Error playing video after metadata:", err);
            });
          }
        };
      }

      setIsActive(true);
    } catch (err) {
      console.error("Error accessing webcam:", err);
      setError(
        err.name === "NotAllowedError"
          ? "Camera permission denied"
          : err.name === "NotFoundError"
          ? "No camera found"
          : "Failed to access camera"
      );
      setIsActive(false);
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
    }
  };

  const stopWebcam = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsActive(false);
    setError("");
  };

  // Handle video element when it becomes available
  useEffect(() => {
    const video = videoRef.current;
    if (video && streamRef.current && isActive) {
      if (video.srcObject !== streamRef.current) {
        video.srcObject = streamRef.current;
      }
      video.play().catch((err) => {
        console.error("Error playing video:", err);
      });
    }
  }, [isActive]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopWebcam();
    };
  }, []);

  return (
    <div
      className={`absolute text-white transition-all duration-300 ${
        isFullscreen
          ? "inset-0 w-full h-full z-20"
          : "bottom-4 right-4 w-[400px]"
      }`}
    >
      <div
        className={`bg-black/70 backdrop-blur-md rounded-lg border border-gray-700/50 shadow-2xl transition-all duration-300 ${
          isFullscreen ? "h-full flex flex-col" : "p-4 space-y-3"
        }`}
      >
        {/* Header */}
        <div
          className={`flex items-center justify-between ${
            isFullscreen ? "p-4 border-b border-gray-700/50" : ""
          }`}
        >
          <h3 className="text-sm font-semibold text-gray-200">Video Camera</h3>
          <div className="flex items-center gap-2">
            {isActive && (
              <button
                onClick={onToggleFullscreen}
                className="flex items-center gap-2 text-xs border rounded-md px-3 py-1.5 transition-colors cursor-pointer bg-blue-600/20 hover:bg-blue-600/30 border-blue-500/30 text-blue-300"
                title={isFullscreen ? "Minimize" : "Fullscreen"}
              >
                {isFullscreen ? (
                  <>
                    <Minimize2 className="w-4 h-4" />
                    Minimize
                  </>
                ) : (
                  <>
                    <Maximize2 className="w-4 h-4" />
                    Fullscreen
                  </>
                )}
              </button>
            )}
            <button
              onClick={isActive ? stopWebcam : startWebcam}
              className={`flex items-center gap-2 text-xs border rounded-md px-3 py-1.5 transition-colors cursor-pointer ${
                isActive
                  ? "bg-red-600/20 hover:bg-red-600/30 border-red-500/30 text-red-300"
                  : "bg-green-600/20 hover:bg-green-600/30 border-green-500/30 text-green-300"
              }`}
            >
              {isActive ? (
                <>
                  <VideoOff className="w-4 h-4" />
                  Stop
                </>
              ) : (
                <>
                  <Video className="w-4 h-4" />
                  Start
                </>
              )}
            </button>
          </div>
        </div>

        {/* Video container */}
        <div
          className={`relative bg-black rounded-lg overflow-hidden border border-gray-700/50 ${
            isFullscreen ? "flex-1 m-4" : "w-full aspect-video"
          }`}
        >
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="w-full h-full object-cover cursor-pointer"
            onClick={isActive && !isFullscreen ? onToggleFullscreen : undefined}
            title={isActive && !isFullscreen ? "Click to expand" : undefined}
          />
          {!isActive && (
            <div className="absolute inset-0 w-full h-full flex items-center justify-center bg-black/90 z-10">
              <div className="text-center space-y-2">
                <VideoOff className="w-12 h-12 mx-auto text-gray-500" />
                <p className="text-xs text-gray-400">
                  {error || "Camera not active"}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Status indicator */}
        {isActive && !isFullscreen && (
          <div className="flex items-center gap-2 text-xs px-4 pb-4">
            <span className="h-2 w-2 rounded-full bg-green-400 animate-pulse"></span>
            <span className="text-gray-300">Live</span>
            <span className="text-gray-500 text-[10px] ml-auto">
              Click video to expand
            </span>
          </div>
        )}
        {isActive && isFullscreen && (
          <div className="flex items-center gap-2 text-xs px-4 pb-4">
            <span className="h-2 w-2 rounded-full bg-green-400 animate-pulse"></span>
            <span className="text-gray-300">Live</span>
          </div>
        )}
      </div>
    </div>
  );
}
