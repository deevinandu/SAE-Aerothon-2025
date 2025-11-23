import React from 'react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip } from 'recharts';
import { LucideIcon } from 'lucide-react';

interface TelemetryWidgetProps {
    title: string;
    value: string | number;
    unit?: string;
    icon: LucideIcon;
    data?: any[];
    dataKey?: string;
    color?: string;
    className?: string;
}

export const TelemetryWidget: React.FC<TelemetryWidgetProps> = ({
    title,
    value,
    unit,
    icon: Icon,
    data,
    dataKey,
    color = "#00f3ff", // Default to Cyan
    className = "",
}) => {
    return (
        <div className={`glass-panel rounded-xl p-4 flex flex-col justify-between overflow-hidden relative ${className}`}>
            {/* Header */}
            <div className="flex items-center justify-between mb-2 z-10">
                <div className="flex items-center gap-2 text-muted-foreground">
                    <Icon size={18} />
                    <span className="text-sm font-medium uppercase tracking-wider">{title}</span>
                </div>
            </div>

            {/* Main Value */}
            <div className="flex items-baseline gap-1 z-10 mb-2">
                <span className="text-3xl font-bold text-white">{value}</span>
                {unit && <span className="text-sm text-muted-foreground font-medium">{unit}</span>}
            </div>

            {/* Chart Background */}
            {data && dataKey && (
                <div className="absolute bottom-0 left-0 right-0 h-16 opacity-30">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={data}>
                            <defs>
                                <linearGradient id={`gradient-${title}`} x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor={color} stopOpacity={0.8} />
                                    <stop offset="95%" stopColor={color} stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <Area
                                type="monotone"
                                dataKey={dataKey}
                                stroke={color}
                                fill={`url(#gradient-${title})`}
                                strokeWidth={2}
                                isAnimationActive={false}
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            )}
        </div>
    );
};
