"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AnalysisResult, SessionState } from "@/types";
import { Eye, Clock, Target, Layers } from "lucide-react";
import { formatLatency } from "@/lib/utils";

interface AnalysisDisplayProps {
  result: AnalysisResult | null;
  latency: number | null;
  isAnalyzing: boolean;
  sessionState?: SessionState;
}

export function AnalysisDisplay({
  result,
  latency,
  isAnalyzing,
  sessionState,
}: AnalysisDisplayProps) {
  if (!result && !isAnalyzing) {
    return (
      <Card className="h-80">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Eye className="h-5 w-5" />
            AI Analysis
          </CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-center h-48 text-muted-foreground">
          <div className="text-center">
            <Target className="h-12 w-12 mx-auto mb-2 opacity-50" />
            <p>Start recording to begin AI analysis</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="h-80">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Eye className="h-5 w-5" />
            AI Analysis
          </div>
          {latency && (
            <div className="flex items-center gap-1 text-sm text-muted-foreground">
              <Clock className="h-4 w-4" />
              {formatLatency(latency)}
            </div>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {isAnalyzing && (
          <div className="flex items-center gap-2 text-sm text-blue-500">
            <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full" />
            Analyzing frame...
          </div>
        )}

        {result && (
          <>
            {/* Current Frame Detected Objects */}
            <div>
              <h4 className="font-medium mb-2 flex items-center gap-2">
                <Layers className="h-4 w-4" />
                Current Frame
              </h4>
              <div className="flex flex-wrap gap-1">
                {result.labels && result.labels.length > 0 ? (
                  result.labels.map((label, index) => (
                    <Badge key={index} variant="outline" className="text-xs">
                      {label || "Unknown"}
                    </Badge>
                  ))
                ) : (
                  <span className="text-sm text-muted-foreground">
                    No objects detected
                  </span>
                )}
              </div>
            </div>

            {/* All Unique Objects Detected */}
            {sessionState &&
              Object.keys(sessionState.unique_objects).length > 0 && (
                <div>
                  <h4 className="font-medium mb-2 flex items-center gap-2">
                    <Target className="h-4 w-4" />
                    All Detected Objects
                  </h4>
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(sessionState.unique_objects)
                      .slice(0, 8)
                      .map(([id, obj]) => (
                        <Badge key={id} variant="outline" className="text-xs">
                          {obj.label}
                        </Badge>
                      ))}
                    {Object.keys(sessionState.unique_objects).length > 8 && (
                      <div className="text-xs text-muted-foreground">
                        +{Object.keys(sessionState.unique_objects).length - 8}{" "}
                        more
                      </div>
                    )}
                  </div>
                </div>
              )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
