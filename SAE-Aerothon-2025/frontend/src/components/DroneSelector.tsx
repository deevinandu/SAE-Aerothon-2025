"use client";

import React from "react";
import { Badge } from "@/components/ui/badge";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Wifi, WifiOff, Battery, Plane } from "lucide-react";

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

interface DroneSelectorProps {
    drones: DroneStatus[];
    selectedDrone: number;
    onSelect: (droneId: number) => void;
}

export const DroneSelector: React.FC<DroneSelectorProps> = ({
    drones,
    selectedDrone,
    onSelect,
}) => {
    const selectedDroneData = drones.find((d) => d.sys_id === selectedDrone);

    const getBatteryColor = (percentage: number) => {
        if (percentage > 50) return "text-green-500";
        if (percentage > 20) return "text-yellow-500";
        return "text-red-500";
    };

    const getStatusColor = (drone: DroneStatus) => {
        if (!drone.connected) return "bg-gray-500";
        if (drone.armed) return "bg-green-500";
        return "bg-yellow-500";
    };

    return (
        <div className="flex items-center gap-2">
            <Plane className="h-4 w-4 text-muted-foreground" />

            <Select
                value={selectedDrone.toString()}
                onValueChange={(value) => onSelect(parseInt(value))}
            >
                <SelectTrigger className="w-[180px]">
                    <SelectValue>
                        {selectedDroneData ? (
                            <div className="flex items-center gap-2">
                                <div
                                    className={`w-2 h-2 rounded-full ${getStatusColor(
                                        selectedDroneData
                                    )}`}
                                />
                                <span>Drone {selectedDrone}</span>
                                <Battery
                                    className={`h-3 w-3 ${getBatteryColor(
                                        selectedDroneData.battery_remaining
                                    )}`}
                                />
                                <span className="text-xs">
                                    {selectedDroneData.battery_remaining}%
                                </span>
                            </div>
                        ) : (
                            `Drone ${selectedDrone}`
                        )}
                    </SelectValue>
                </SelectTrigger>
                <SelectContent>
                    {drones.length === 0 ? (
                        <SelectItem value="0" disabled>
                            No drones connected
                        </SelectItem>
                    ) : (
                        drones.map((drone) => (
                            <SelectItem key={drone.sys_id} value={drone.sys_id.toString()}>
                                <div className="flex items-center gap-2 w-full">
                                    <div
                                        className={`w-2 h-2 rounded-full ${getStatusColor(drone)}`}
                                    />
                                    <span className="flex-1">Drone {drone.sys_id}</span>
                                    <Badge
                                        variant={drone.armed ? "default" : "secondary"}
                                        className="text-xs"
                                    >
                                        {drone.mode}
                                    </Badge>
                                    <div className="flex items-center gap-1">
                                        <Battery
                                            className={`h-3 w-3 ${getBatteryColor(
                                                drone.battery_remaining
                                            )}`}
                                        />
                                        <span className="text-xs">{drone.battery_remaining}%</span>
                                    </div>
                                    {drone.connected ? (
                                        <Wifi className="h-3 w-3 text-green-500" />
                                    ) : (
                                        <WifiOff className="h-3 w-3 text-red-500" />
                                    )}
                                </div>
                            </SelectItem>
                        ))
                    )}
                </SelectContent>
            </Select>

            {selectedDroneData && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Badge variant={selectedDroneData.armed ? "default" : "secondary"}>
                        {selectedDroneData.mode}
                    </Badge>
                    {selectedDroneData.connected ? (
                        <Wifi className="h-3 w-3 text-green-500" />
                    ) : (
                        <WifiOff className="h-3 w-3 text-red-500" />
                    )}
                </div>
            )}
        </div>
    );
};
