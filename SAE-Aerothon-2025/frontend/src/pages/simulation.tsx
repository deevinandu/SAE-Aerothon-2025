import React, { useState } from 'react';
import { DashboardLayout } from '../components/DashboardLayout';
import { Navbar } from './dashboard/components/Navbar';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Upload, AlertTriangle, CheckCircle, Brain } from 'lucide-react';

export default function SimulationPage() {
    const [selectedImage, setSelectedImage] = useState<string | null>(null);
    const [analysisResult, setAnalysisResult] = useState<any>(null);
    const [loading, setLoading] = useState(false);

    const handleImageUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        // Preview
        const reader = new FileReader();
        reader.onload = (e) => setSelectedImage(e.target?.result as string);
        reader.readAsDataURL(file);

        // Analyze
        setLoading(true);
        setAnalysisResult(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('http://localhost:8000/test/analyze_image', {
                method: 'POST',
                body: formData,
            });
            const data = await response.json();
            setAnalysisResult(data);
        } catch (error) {
            console.error("Analysis failed", error);
        } finally {
            setLoading(false);
        }
    };

    return (
        <DashboardLayout>
            <div className="col-span-1 md:col-span-12">
                <Navbar
                    videoSource={{ type: 'Webcam', connectionString: '', isActive: false }}
                    onSourceChange={() => { }}
                    onConnect={() => { }}
                    onDisconnect={() => { }}
                    isConnected={false}
                />
            </div>

            <div className="col-span-1 md:col-span-12 mb-8">
                <h1 className="text-3xl font-bold text-white mb-2">Simulation Mode</h1>
                <p className="text-muted-foreground">Test Gemini's detection capabilities by uploading static images of disasters.</p>
            </div>

            <div className="col-span-1 md:col-span-6">
                <Card className="h-full">
                    <CardHeader>
                        <CardTitle>Upload Test Image</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="flex flex-col items-center justify-center border-2 border-dashed border-muted-foreground/25 rounded-lg p-12 hover:bg-muted/5 transition-colors">
                            <input
                                type="file"
                                accept="image/*"
                                onChange={handleImageUpload}
                                className="hidden"
                                id="image-upload"
                            />
                            <label htmlFor="image-upload" className="cursor-pointer flex flex-col items-center">
                                <Upload className="h-12 w-12 text-muted-foreground mb-4" />
                                <span className="text-lg font-medium text-white">Click to Upload Image</span>
                                <span className="text-sm text-muted-foreground mt-2">JPG, PNG supported</span>
                            </label>
                        </div>

                        {selectedImage && (
                            <div className="mt-6 rounded-lg overflow-hidden border border-border">
                                <img src={selectedImage} alt="Test" className="w-full h-auto" />
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>

            <div className="col-span-1 md:col-span-6">
                <Card className="h-full">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2">
                            <Brain className="text-secondary" />
                            AI Analysis Result
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        {loading && (
                            <div className="flex items-center justify-center h-64">
                                <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
                                <span className="ml-3 text-muted-foreground">Analyzing image...</span>
                            </div>
                        )}

                        {!loading && analysisResult && (
                            <div className="space-y-6">
                                {/* Status Badges */}
                                <div className="flex flex-wrap gap-3">
                                    <div className={`px-4 py-2 rounded-full border ${analysisResult.disaster_detected ? 'bg-destructive/20 border-destructive text-destructive' : 'bg-muted border-border text-muted-foreground'}`}>
                                        {analysisResult.disaster_detected ? '🚨 Disaster Detected' : 'No Disaster'}
                                    </div>
                                    <div className={`px-4 py-2 rounded-full border ${analysisResult.human_detected ? 'bg-orange-500/20 border-orange-500 text-orange-500' : 'bg-muted border-border text-muted-foreground'}`}>
                                        {analysisResult.human_detected ? '👤 Human Detected' : 'No Humans'}
                                    </div>
                                    <div className={`px-4 py-2 rounded-full border ${analysisResult.safe_spot_detected ? 'bg-green-500/20 border-green-500 text-green-500' : 'bg-muted border-border text-muted-foreground'}`}>
                                        {analysisResult.safe_spot_detected ? '✅ Safe Spot Found' : 'No Safe Spot'}
                                    </div>
                                </div>

                                {/* Reasoning */}
                                <div className="bg-muted/30 p-4 rounded-lg border border-border">
                                    <h3 className="text-sm font-bold text-white mb-2 uppercase tracking-wider">Reasoning</h3>
                                    <p className="text-gray-300 leading-relaxed">{analysisResult.reasoning}</p>
                                </div>

                                {/* Raw JSON */}
                                <div className="bg-black/50 p-4 rounded-lg border border-border font-mono text-xs overflow-auto max-h-64">
                                    <pre>{JSON.stringify(analysisResult, null, 2)}</pre>
                                </div>
                            </div>
                        )}

                        {!loading && !analysisResult && (
                            <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
                                <p>Upload an image to see the analysis result.</p>
                            </div>
                        )}
                    </CardContent>
                </Card>
            </div>
        </DashboardLayout>
    );
}
