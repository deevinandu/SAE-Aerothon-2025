"use client";

import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { VideoSource } from "@/types";
import {
  Wifi,
  WifiOff,
  Video,
  Radio,
  Rss,
  Globe,
  FileVideo,
  ChevronDown,
  Circle,
  Square,
} from "lucide-react";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { MissionControlWidget } from "@/components/MissionControlWidget";
import { DroneSelector } from "@/components/DroneSelector";
import { ConnectionDialog } from "@/components/ConnectionDialog";

interface NavbarProps {
  videoSource: VideoSource;
  onSourceChange: (source: VideoSource) => void;
  onConnect: () => void;
  onDisconnect: () => void;
  isConnected: boolean;
  drones?: any[];
  selectedDrone?: number;
  onSelectDrone?: (id: number) => void;
}

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export const Navbar: React.FC<NavbarProps> = ({
  videoSource,
  onSourceChange,
  onConnect,
  onDisconnect,
  isConnected,
  drones = [],
  selectedDrone = 1,
  onSelectDrone = () => { },
}: NavbarProps) => {
  const [isDropdownOpen, setIsDropdownOpen] = React.useState(false);
  const [connectionString, setConnectionString] = React.useState("");
  const [isRecording, setIsRecording] = React.useState(false);
  const [recordingDuration, setRecordingDuration] = React.useState(0);
  const [sessionId, setSessionId] = React.useState("");

  React.useEffect(() => {
    setConnectionString(videoSource.connectionString);
  }, [videoSource.connectionString]);

  React.useEffect(() => {
    let timer: NodeJS.Timeout;
    if (isRecording) {
      timer = setInterval(() => {
        setRecordingDuration((prevDuration) => prevDuration + 1);
      }, 1000);
    } else {
      setRecordingDuration(0);
    }
    return () => clearInterval(timer);
  }, [isRecording]);

  const handleSourceTypeChange = (type: VideoSource["type"]) => {
    const newSource: VideoSource = {
      type,
      connectionString: type === "Webcam" ? "" : connectionString,
      isActive: false,
    };
    onSourceChange(newSource);
    setIsDropdownOpen(false);
  };

  const handleConnectionStringChange = (value: string) => {
    setConnectionString(value);
    onSourceChange({
      ...videoSource,
      connectionString: value,
    });
  };

  const handleConnect = () => {
    onConnect();
  };

  const handleDisconnect = () => {
    // Stop recording if active
    if (isRecording) {
      handleStopRecording();
    }
    onDisconnect();
  };

  const handleStartRecording = async () => {
    try {
      const newSessionId = `session_${Date.now()}`;
      const response = await fetch(`${BACKEND_URL}/recording/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: newSessionId }),
      });

      if (response.ok) {
        setIsRecording(true);
        setSessionId(newSessionId);
        setRecordingDuration(0);
      }
    } catch (error) {
      console.error("Failed to start recording:", error);
    }
  };

  const handleStopRecording = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/recording/stop`, {
        method: "POST",
      });

      if (response.ok) {
        setIsRecording(false);
        setRecordingDuration(0);
      }
    } catch (error) {
      console.error("Failed to stop recording:", error);
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const sourceIcons = {
    Webcam: Video,
    UDP: Radio,
    TCP: Radio,
    RTSP: Rss,
    HTTP: Globe,
    File: FileVideo,
  };

  const SourceIcon = sourceIcons[videoSource.type];
  const sourceTypes = Object.keys(sourceIcons) as VideoSource["type"][];

  return (
    <Card className="w-full mb-0 border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <CardContent className="py-1 px-4">
        <div className="flex items-center gap-4">
          {/* Connection Status */}
          <div className="flex items-center gap-2">
            <Badge
              variant={isConnected ? "default" : "secondary"}
              className="flex items-center gap-1"
            >
              {isConnected ? (
                <>
                  <Wifi className="h-3 w-3" />
                  Connected
                </>
              ) : (
                <>
                  <WifiOff className="h-3 w-3" />
                  Disconnected
                </>
              )}
            </Badge>
          </div>

          {/* Drone Selector */}
          {drones.length > 0 && (
            <DroneSelector
              drones={drones}
              selectedDrone={selectedDrone}
              onSelect={onSelectDrone}
            />
          )}

          {/* MAVLink Connection */}
          <ConnectionDialog />

          <div className="relative">
            <Button
              variant="outline"
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              className="flex items-center gap-2 h-8"
            >
              <SourceIcon className="h-4 w-4" />
              {videoSource.type}
              <ChevronDown className="h-4 w-4" />
            </Button>

            {isDropdownOpen && (
              <div className="absolute top-full left-0 mt-1 bg-popover border rounded-md shadow-lg z-50 min-w-[120px]">
                {sourceTypes.map((type) => {
                  const Icon = sourceIcons[type];
                  return (
                    <button
                      key={type}
                      onClick={() => handleSourceTypeChange(type)}
                      className="w-full px-3 py-2 text-left hover:bg-accent hover:text-accent-foreground flex items-center gap-2 first:rounded-t-md last:rounded-b-md cursor-pointer text-sm"
                    >
                      <Icon className="h-4 w-4" />
                      {type}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Connection String Input */}
          {videoSource.type !== "Webcam" && (
            <div className="flex-1 max-w-md">
              <Input
                placeholder={getPlaceholderForSourceType(videoSource.type)}
                value={connectionString}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  handleConnectionStringChange(e.target.value)
                }
                className="w-full h-8"
              />
            </div>
          )}

          {/* Connect/Disconnect Buttons */}
          <div className="flex gap-2">
            {isConnected ? (
              <Button
                variant="destructive"
                onClick={handleDisconnect}
                size="sm"
                className="h-8"
              >
                <WifiOff className="h-4 w-4 mr-2" />
                Disconnect
              </Button>
            ) : (
              <Button
                onClick={handleConnect}
                size="sm"
                className="h-8"
                disabled={
                  videoSource.type !== "Webcam" && !connectionString.trim()
                }
              >
                <Wifi className="h-4 w-4 mr-2" />
                Connect
              </Button>
            )}
          </div>

          {/* Spacer */}
          <div className="flex-1" />

          {/* Right Side Controls */}
          <div className="flex items-center gap-2">
            {/* Mission Control Popover */}
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="h-8 gap-2 border-primary/50 text-primary hover:bg-primary/10">
                  <Globe className="h-4 w-4" />
                  Mission Control
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-80 p-0 bg-transparent border-none shadow-none" align="end">
                <MissionControlWidget className="w-full shadow-xl border border-border/50 bg-background/95 backdrop-blur" />
              </PopoverContent>
            </Popover>

            {/* Recording Button */}
            {isConnected && (
              <Button
                variant={isRecording ? "destructive" : "outline"}
                onClick={isRecording ? handleStopRecording : handleStartRecording}
                size="sm"
                className="h-8 gap-2"
              >
                {isRecording ? (
                  <>
                    <Square className="h-3 w-3 fill-current" />
                    {formatDuration(recordingDuration)}
                  </>
                ) : (
                  <>
                    <Circle className="h-3 w-3" />
                    Record
                  </>
                )}
              </Button>
            )}

            {/* Simulation Mode Button */}
            <Button
              variant="secondary"
              onClick={() => window.location.href = '/simulation'}
              size="sm"
              className="h-8"
            >
              <FileVideo className="h-4 w-4 mr-2" />
              Simulation
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function getPlaceholderForSourceType(type: VideoSource["type"]): string {
  switch (type) {
    case "UDP":
      return "udp://127.0.0.1:8554";
    case "TCP":
      return "tcp://127.0.0.1:8554";
    case "RTSP":
      return "rtsp://127.0.0.1:8554/stream";
    case "HTTP":
      return "http://127.0.0.1:8080/stream";
    case "File":
      return "/path/to/video.mp4";
    default:
      return "Enter connection details...";
  }
}
