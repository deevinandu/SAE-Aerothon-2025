import React, { useRef } from 'react';
import { Activity, Brain, Navigation2, AlertTriangle } from 'lucide-react';

interface MissionEvent {
    type: string;
    event_type?: string;
    message: string;
    timestamp: number;
    disaster_detected?: boolean;
    reasoning?: string;
}

interface MissionLogWidgetProps {
    events: MissionEvent[];
    className?: string;
}

export const MissionLogWidget: React.FC<MissionLogWidgetProps> = ({ events, className = "" }) => {
    const logEndRef = useRef<HTMLDivElement>(null);

    // No auto-scroll needed since newest events are at the top

    const getEventIcon = (event: MissionEvent) => {
        if (event.type === 'mission_event') {
            if (event.event_type === 'navigation') return <Navigation2 size={14} className="text-primary" />;
            if (event.event_type === 'disaster_response') return <AlertTriangle size={14} className="text-destructive" />;
            if (event.event_type === 'error') return <AlertTriangle size={14} className="text-destructive" />;
        }
        // AI analysis events
        return <Brain size={14} className="text-secondary" />;
    };

    const getEventColor = (event: MissionEvent) => {
        if (event.type === 'mission_event') {
            if (event.event_type === 'navigation') return 'border-l-primary';
            if (event.event_type === 'disaster_response') return 'border-l-destructive';
            if (event.event_type === 'error') return 'border-l-destructive';
        }
        // AI analysis
        if (event.disaster_detected) return 'border-l-destructive';
        return 'border-l-secondary';
    };

    const formatMessage = (event: MissionEvent) => {
        if (event.type === 'mission_event') {
            return event.message;
        }
        // AI analysis event
        if (event.reasoning) {
            return `AI: ${event.reasoning}`;
        }
        return event.message || 'Unknown event';
    };

    const formatTime = (timestamp: number) => {
        const date = new Date(timestamp * 1000);
        return date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    };

    return (
        <div className={`glass-panel rounded-xl p-2 flex flex-col ${className}`}>
            {/* Header */}
            <div className="flex items-center gap-2 text-muted-foreground mb-1 pb-1 border-b border-border/30">
                <Activity size={16} className="text-primary" />
                <span className="text-xs font-medium uppercase tracking-wider">Mission Log</span>
                <span className="text-[10px] text-muted-foreground ml-auto">{events.length} events</span>
            </div>

            {/* Log Entries - Reversed to show newest first, shows ~5 entries */}
            <div className="flex-1 overflow-y-auto space-y-1 min-h-[150px] max-h-[220px]">
                {events.length === 0 ? (
                    <div className="flex items-center justify-center h-full text-xs text-muted-foreground">
                        No events yet
                    </div>
                ) : (
                    [...events].reverse().map((event, index) => (
                        <div
                            key={index}
                            className={`flex items-start gap-2 p-2 rounded border-l-2 bg-black/20 ${getEventColor(event)}`}
                        >
                            <div className="mt-0.5">{getEventIcon(event)}</div>
                            <div className="flex-1 min-w-0">
                                <div className="text-xs text-white break-words">{formatMessage(event)}</div>
                            </div>
                            <div className="text-[10px] text-muted-foreground whitespace-nowrap">
                                {formatTime(event.timestamp)}
                            </div>
                        </div>
                    ))
                )}
                <div ref={logEndRef} />
            </div>
        </div>
    );
};
