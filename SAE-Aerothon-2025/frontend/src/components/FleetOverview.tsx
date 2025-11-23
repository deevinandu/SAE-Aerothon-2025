"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Battery, Plane, MapPin, Wifi, WifiOff } from "lucide-react";

interface DroneStatus {
    sys_id: number;
    mode: string;
    armed: boolean;
    battery_remaining: number;
    battery_voltage: number;
    latitude: number;
    longitude: number;
    altitude: number;
    connected?: boolean;
}

interface FleetOverviewProps {
    drones: DroneStatus[];
    selectedDrone: number;
    onSelectDrone: (droneId: number) => void;
}

export const FleetOverview: React.FC<FleetOverviewProps> = ({
    drones,
    selectedDrone,
    onSelectDrone,
}) => {
    const getBatteryColor = (percentage: number) => {
        if (percentage > 50) return "text-green-500";
        if (percentage > 20) return "text-yellow-500";
        return "text-red-500";
    };

    const getStatusColor = (drone: DroneStatus) => {
        if (!drone.connected) return "border-gray-500 bg-gray-50";
        if (drone.armed) return "border-green-500 bg-green-50";
        return "border-yellow-500 bg-yellow-50";
    };

    if (drones.length === 0) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="text-sm">Fleet Overview</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="text-center text-muted-foreground text-sm py-4">
                        No drones connected
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card>
            <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                    <Plane className="h-4 w-4" />
                    Fleet Overview ({drones.length})
                </CardTitle>
            </CardHeader>
            <CardContent>
                <div className="grid grid-cols-2 gap-2">
                    {drones.map((drone) => (
                        <div
                            key={drone.sys_id}
                            onClick={() => onSelectDrone(drone.sys_id)}
                            className={`
                p-3 rounded-lg border-2 cursor-pointer transition-all
                ${getStatusColor(drone)}
                ${selectedDrone === drone.sys_id
                                    ? "ring-2 ring-primary"
                                    : "hover:ring-1 hover:ring-primary/50"
                                }
              `}
                        >
                            {/* Header */}
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                    <Plane className="h-4 w-4" />
                                    <span className="font-semibold text-sm">
                                        Drone {drone.sys_id}
                                    </span>
                                </div>
                                {drone.connected ? (
                                    <Wifi className="h-3 w-3 text-green-500" />
                                ) : (
                                    <WifiOff className="h-3 w-3 text-red-500" />
                                )}
                            </div>

                            {/* Status */}
                            <div className="space-y-1">
                                <div className="flex items-center justify-between">
                                    <Badge
                                        variant={drone.armed ? "default" : "secondary"}
                                        className="text-xs"
                                    >
                                        {drone.mode}
                                    </Badge>
                                    {drone.armed && (
                                        <Badge variant="destructive" className="text-xs">
                                            ARMED
                                        </Badge>
                                    )}
                                </div>

                                {/* Battery */}
                                <div className="flex items-center gap-1 text-xs">
                                    <Battery
                                        className={`h-3 w-3 ${getBatteryColor(
                                            drone.battery_remaining
                                        )}`}
                                    />
                                    <span className={getBatteryColor(drone.battery_remaining)}>
                                        {drone.battery_remaining}%
                                    </span>
                                    <span className="text-muted-foreground">
                                        ({drone.battery_voltage.toFixed(1)}V)
                                    </span>
                                </div>

                                {/* Altitude */}
                                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                                    <MapPin className="h-3 w-3" />
                                    <span>{drone.altitude.toFixed(1)}m</span>
                                </div>

                                {/* GPS */}
                                {drone.latitude !== 0 && drone.longitude !== 0 && (
                                    <div className="text-xs text-muted-foreground truncate">
                                        {drone.latitude.toFixed(4)}, {drone.longitude.toFixed(4)}
                                    </div>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            </CardContent>
        </Card>
    );
};
