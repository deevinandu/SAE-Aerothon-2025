"use client";

import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from "@/components/ui/dialog";
import { Settings, Wifi } from "lucide-react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

interface ConnectionDialogProps {
    onConnectionChange?: (connected: boolean) => void;
}

export const ConnectionDialog: React.FC<ConnectionDialogProps> = ({ onConnectionChange }) => {
    const [protocol, setProtocol] = useState("UDP");
    const [host, setHost] = useState("127.0.0.1");
    const [port, setPort] = useState("14550");
    const [serialPort, setSerialPort] = useState("COM3");
    const [baud, setBaud] = useState("57600");
    const [isConnecting, setIsConnecting] = useState(false);
    const [status, setStatus] = useState("");
    const [open, setOpen] = useState(false);

    const handleConnect = async () => {
        setIsConnecting(true);
        setStatus("Connecting...");

        try {
            const payload: any = { protocol };

            if (protocol === "UDP" || protocol === "TCP") {
                payload.host = host;
                payload.port = parseInt(port);
            } else if (protocol === "SERIAL") {
                payload.port = serialPort;
                payload.baud = parseInt(baud);
            }

            const response = await fetch(`${BACKEND_URL}/telemetry/connect`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });

            const data = await response.json();

            if (response.ok) {
                setStatus("✅ Connected successfully!");
                onConnectionChange?.(true);
                setTimeout(() => setOpen(false), 1500);
            } else {
                setStatus(`❌ Error: ${data.detail || "Connection failed"}`);
            }
        } catch (error) {
            setStatus(`❌ Error: ${error}`);
        } finally {
            setIsConnecting(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2">
                    <Settings className="h-4 w-4" />
                    MAVLink
                </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Wifi className="h-5 w-5" />
                        MAVLink Connection
                    </DialogTitle>
                    <DialogDescription>
                        Connect to your drone or simulator
                    </DialogDescription>
                </DialogHeader>

                <div className="grid gap-4 py-4">
                    <div className="grid gap-2">
                        <Label htmlFor="protocol">Protocol</Label>
                        <Select value={protocol} onValueChange={setProtocol}>
                            <SelectTrigger id="protocol">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent position="popper" sideOffset={5} className="bg-black border-border">
                                <SelectItem value="UDP">UDP (SITL/Network)</SelectItem>
                                <SelectItem value="TCP">TCP</SelectItem>
                                <SelectItem value="SERIAL">Serial (USB)</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {(protocol === "UDP" || protocol === "TCP") && (
                        <>
                            <div className="grid gap-2">
                                <Label htmlFor="host">Host</Label>
                                <Input
                                    id="host"
                                    value={host}
                                    onChange={(e) => setHost(e.target.value)}
                                    placeholder="127.0.0.1"
                                />
                            </div>
                            <div className="grid gap-2">
                                <Label htmlFor="port">Port</Label>
                                <Input
                                    id="port"
                                    value={port}
                                    onChange={(e) => setPort(e.target.value)}
                                    placeholder="14550"
                                />
                            </div>
                        </>
                    )}

                    {protocol === "SERIAL" && (
                        <>
                            <div className="grid gap-2">
                                <Label htmlFor="serialPort">Serial Port</Label>
                                <Input
                                    id="serialPort"
                                    value={serialPort}
                                    onChange={(e) => setSerialPort(e.target.value)}
                                    placeholder="COM3"
                                />
                            </div>
                            <div className="grid gap-2">
                                <Label htmlFor="baud">Baud Rate</Label>
                                <Select value={baud} onValueChange={setBaud}>
                                    <SelectTrigger id="baud">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent position="popper" sideOffset={5} className="bg-black border-border">
                                        <SelectItem value="9600">9600</SelectItem>
                                        <SelectItem value="57600">57600</SelectItem>
                                        <SelectItem value="115200">115200</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </>
                    )}

                    {status && (
                        <div className="text-sm text-center p-2 rounded bg-muted">
                            {status}
                        </div>
                    )}

                    <Button
                        onClick={handleConnect}
                        disabled={isConnecting}
                        className="w-full"
                    >
                        {isConnecting ? "Connecting..." : "Connect"}
                    </Button>

                    <div className="text-xs text-muted-foreground space-y-1">
                        <p className="font-semibold">Quick Presets:</p>
                        <p>• SITL: UDP, 127.0.0.1:14550</p>
                        <p>• Real Drone: Serial, COM3, 57600</p>
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
};
