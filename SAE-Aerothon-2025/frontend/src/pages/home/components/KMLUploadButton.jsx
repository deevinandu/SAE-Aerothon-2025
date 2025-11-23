"use client";

import React, { useRef } from "react";
import { Upload } from "lucide-react";

export default function KMLUploadButton({ onKMLLoaded }) {
  const fileInputRef = useRef(null);

  const handleFileSelect = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith(".kml") && !file.name.endsWith(".kmz")) {
      alert("Please select a valid KML or KMZ file");
      return;
    }

    try {
      const text = await file.text();
      if (onKMLLoaded) {
        onKMLLoaded(text, file.name);
      }
      console.log("KML file loaded:", file.name);
      // You can add visual feedback here
      alert(`KML file "${file.name}" loaded successfully!`);
    } catch (error) {
      console.error("Error reading KML file:", error);
      alert("Failed to read KML file");
    }

    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept=".kml,.kmz"
        onChange={handleFileSelect}
        className="hidden"
      />
      <button
        onClick={() => fileInputRef.current?.click()}
        className="absolute top-4 left-1/2 -translate-x-1/2 bg-black/70 hover:bg-black/80 backdrop-blur-md text-white p-3 rounded-full border border-gray-700/50 shadow-2xl transition-all hover:scale-105 group"
        title="Upload KML file"
      >
        <Upload className="h-5 w-5 group-hover:text-blue-400 transition-colors" />
      </button>
    </>
  );
}
