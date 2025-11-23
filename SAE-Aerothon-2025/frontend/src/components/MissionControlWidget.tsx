import React, { useState } from 'react';
import { Upload, Play, Map, AlertTriangle, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface MissionControlWidgetProps {
    className?: string;
}

export const MissionControlWidget: React.FC<MissionControlWidgetProps> = ({ className = "" }) => {
    const [file, setFile] = useState<File | null>(null);
    const [altitude, setAltitude] = useState<string>("50");
    const [speed, setSpeed] = useState<string>("5");
    const [status, setStatus] = useState<string>("");
    const [isUploading, setIsUploading] = useState(false);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
            setStatus("");
        }
    };

    const handleStartMission = async () => {
        if (!file) {
            setStatus("Please select a KML file first.");
            return;
        }

        setIsUploading(true);
        setStatus("Uploading mission...");

        const formData = new FormData();
        formData.append('kml_file', file);
        formData.append('altitude', altitude);
        formData.append('speed', speed);
        formData.append('auto_start', 'true');
        formData.append('use_drone_position', 'true');

        try {
            const response = await fetch('http://localhost:8000/mission/start', {
                method: 'POST',
                body: formData,
            });

            if (response.ok) {
                const data = await response.json();
                setStatus("Mission Uploaded & Started! 🚀");
                console.log("Mission Success:", data);
            } else {
                const errorData = await response.json();
                setStatus(`Error: ${errorData.detail || "Upload failed"}`);
            }
        } catch (error) {
            console.error("Mission upload error:", error);
            setStatus("Network Error: Could not reach backend.");
        } finally {
            setIsUploading(false);
        }
    };

    return (
        <div className={`glass-panel rounded-xl p-4 flex flex-col gap-4 ${className}`}>
            {/* Header */}
            <div className="flex items-center gap-2 text-muted-foreground mb-1">
                <Map size={18} className="text-primary" />
                <span className="text-sm font-medium uppercase tracking-wider">Mission Control</span>
            </div>

            {/* File Upload Area */}
            <div className="relative group">
                <input
                    type="file"
                    accept=".kml"
                    onChange={handleFileChange}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                />
                <div className={`border-2 border-dashed rounded-lg p-4 flex flex-col items-center justify-center transition-colors ${file ? 'border-primary/50 bg-primary/10' : 'border-muted-foreground/25 hover:bg-muted/5'}`}>
                    {file ? (
                        <>
                            <CheckCircle className="h-6 w-6 text-primary mb-2" />
                            <span className="text-sm font-medium text-white truncate max-w-full">{file.name}</span>
                            <span className="text-xs text-muted-foreground">Click to change</span>
                        </>
                    ) : (
                        <>
                            <Upload className="h-6 w-6 text-muted-foreground mb-2" />
                            <span className="text-sm font-medium text-muted-foreground">Upload KML File</span>
                        </>
                    )}
                </div>
            </div>

            {/* Parameters */}
            <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                    <Label htmlFor="altitude" className="text-xs text-muted-foreground">Altitude (m)</Label>
                    <Input
                        id="altitude"
                        type="number"
                        value={altitude}
                        onChange={(e) => setAltitude(e.target.value)}
                        className="bg-black/20 border-white/10 text-white h-8 text-sm"
                    />
                </div>
                <div className="space-y-1">
                    <Label htmlFor="speed" className="text-xs text-muted-foreground">Speed (m/s)</Label>
                    <Input
                        id="speed"
                        type="number"
                        value={speed}
                        onChange={(e) => setSpeed(e.target.value)}
                        className="bg-black/20 border-white/10 text-white h-8 text-sm"
                    />
                </div>
            </div>

            {/* Action Button */}
            <Button
                onClick={handleStartMission}
                disabled={isUploading || !file}
                className={`w-full font-bold transition-all ${status.includes("Success") ? "bg-green-500 hover:bg-green-600" : "bg-primary hover:bg-primary/90"}`}
            >
                {isUploading ? (
                    <span className="animate-pulse">Uploading...</span>
                ) : (
                    <>
                        <Play className="mr-2 h-4 w-4" />
                        Start Mission
                    </>
                )}
            </Button>

            {/* Status Message */}
            {status && (
                <div className={`text-xs text-center p-2 rounded ${status.includes("Error") ? "bg-destructive/20 text-destructive" : status.includes("Success") ? "bg-green-500/20 text-green-400" : "text-muted-foreground"}`}>
                    {status}
                </div>
            )}
        </div>
    );
};
