"use client";

import type { KeyboardEvent } from "react";

export type BodyView = "front" | "back";

type Hotspot = { zone: string; cx: number; cy: number; r: number; views: BodyView[] };

const BOTH: BodyView[] = ["front", "back"];

// Un point par articulation ou région, côtés gauche et droit confondus : la bibliothèque classe
// les exercices par zone, pas par côté.
const HOTSPOTS: Hotspot[] = [
  { zone: "neck", cx: 100, cy: 64, r: 11, views: BOTH },
  { zone: "shoulder", cx: 62, cy: 90, r: 13, views: BOTH },
  { zone: "shoulder", cx: 138, cy: 90, r: 13, views: BOTH },
  { zone: "upper_back", cx: 100, cy: 112, r: 18, views: ["back"] },
  { zone: "lower_back", cx: 100, cy: 172, r: 17, views: ["back"] },
  { zone: "elbow", cx: 48, cy: 160, r: 11, views: BOTH },
  { zone: "elbow", cx: 152, cy: 160, r: 11, views: BOTH },
  { zone: "wrist_hand", cx: 37, cy: 222, r: 12, views: BOTH },
  { zone: "wrist_hand", cx: 163, cy: 222, r: 12, views: BOTH },
  { zone: "hip", cx: 82, cy: 216, r: 13, views: BOTH },
  { zone: "hip", cx: 118, cy: 216, r: 13, views: BOTH },
  { zone: "thigh", cx: 82, cy: 268, r: 13, views: BOTH },
  { zone: "thigh", cx: 118, cy: 268, r: 13, views: BOTH },
  { zone: "knee", cx: 82, cy: 318, r: 11, views: ["front"] },
  { zone: "knee", cx: 118, cy: 318, r: 11, views: ["front"] },
  { zone: "lower_leg", cx: 81, cy: 354, r: 11, views: BOTH },
  { zone: "lower_leg", cx: 119, cy: 354, r: 11, views: BOTH },
  { zone: "ankle_foot", cx: 80, cy: 394, r: 11, views: BOTH },
  { zone: "ankle_foot", cx: 120, cy: 394, r: 11, views: BOTH },
];

const BODY_FILL = "#DCE2E9";

type Props = {
  view: BodyView;
  selectedZone: string | null;
  // Zones qui ont des exercices, avec leur libellé : seules celles-ci sont cliquables.
  zones: { id: string; label: string }[];
  onSelect: (zoneId: string) => void;
};

export function BodyMap({ view, selectedZone, zones, onSelect }: Props) {
  const labels = new Map(zones.map((zone) => [zone.id, zone.label]));
  const spots = HOTSPOTS.filter((spot) => spot.views.includes(view) && labels.has(spot.zone));

  const onKeyDown = (event: KeyboardEvent, zone: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(zone);
    }
  };

  return (
    <svg
      viewBox="0 0 200 420"
      role="group"
      aria-label={view === "front" ? "Corps vu de face" : "Corps vu de dos"}
      className="mx-auto h-auto w-full max-w-[220px]"
    >
      <g fill={BODY_FILL} stroke={BODY_FILL} strokeLinecap="round" strokeLinejoin="round">
        <circle cx="100" cy="34" r="20" stroke="none" />
        <rect x="92" y="50" width="16" height="20" stroke="none" />
        <path d="M66 78 Q100 66 134 78 L130 130 Q126 170 126 232 L74 232 Q74 170 70 130 Z" strokeWidth="6" />
        <path d="M60 88 L47 160 L37 224" fill="none" strokeWidth="16" />
        <path d="M140 88 L153 160 L163 224" fill="none" strokeWidth="16" />
        <path d="M85 232 L82 318 L80 392" fill="none" strokeWidth="22" />
        <path d="M115 232 L118 318 L120 392" fill="none" strokeWidth="22" />
        <ellipse cx="76" cy="406" rx="13" ry="5" stroke="none" />
        <ellipse cx="124" cy="406" rx="13" ry="5" stroke="none" />
      </g>
      {view === "back" && (
        <path d="M100 70 L100 232" stroke="#B9C2CD" strokeWidth="2" strokeDasharray="3 4" fill="none" />
      )}
      {spots.map((spot) => {
        const selected = spot.zone === selectedZone;
        return (
          <circle
            key={`${spot.zone}-${spot.cx}`}
            cx={spot.cx}
            cy={spot.cy}
            r={spot.r}
            role="button"
            tabIndex={0}
            aria-label={labels.get(spot.zone)}
            aria-pressed={selected}
            onClick={() => onSelect(spot.zone)}
            onKeyDown={(event) => onKeyDown(event, spot.zone)}
            className={`cursor-pointer outline-none transition-colors focus-visible:stroke-blue-700 focus-visible:stroke-[3] ${
              selected
                ? "fill-blue-600/60 stroke-blue-700 stroke-2"
                : "fill-blue-500/15 stroke-blue-500/60 stroke-1 hover:fill-blue-500/40"
            }`}
          >
            <title>{labels.get(spot.zone)}</title>
          </circle>
        );
      })}
    </svg>
  );
}
