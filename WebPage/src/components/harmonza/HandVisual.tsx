import { type GestureState } from "@/lib/harmonza-engine";
import { cn } from "@/lib/utils";

/**
 * Stylised hand rendered from gesture finger state.
 * Purely presentational — driven by the (simulated) engine output.
 */
export function HandVisual({
  gesture,
  className,
}: {
  gesture: GestureState;
  className?: string;
}) {
  const fingers = gesture.fingers;
  const geometry = [
    { x: 44, base: 168, len: 54, rot: -34 },
    { x: 84, base: 150, len: 86, rot: -10 },
    { x: 112, base: 145, len: 98, rot: 0 },
    { x: 140, base: 150, len: 88, rot: 9 },
    { x: 166, base: 158, len: 66, rot: 20 },
  ];

  return (
    <svg
      viewBox="0 0 220 250"
      className={cn("h-full w-full", className)}
      role="img"
      aria-label={`Hand pose: ${gesture.pose}`}
    >
      <defs>
        <linearGradient id="hz-hand" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--violet)" />
          <stop offset="100%" stopColor="var(--cyan)" />
        </linearGradient>
        <filter id="hz-hand-glow" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="6" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <g filter="url(#hz-hand-glow)" stroke="url(#hz-hand)" fill="none" strokeLinecap="round">
        {/* palm */}
        <rect
          x="58"
          y="150"
          width="112"
          height="86"
          rx="34"
          strokeWidth="4"
          opacity="0.85"
        />
        {/* thumb root */}
        <path d="M58 196 C40 190 34 172 44 162" strokeWidth="4" opacity="0.6" />
        {geometry.map((f, i) => {
          const extended = fingers[i];
          const len = extended ? f.len : f.len * 0.34;
          return (
            <g key={i} transform={`rotate(${f.rot} ${f.x} ${f.base})`}>
              <line
                x1={f.x}
                y1={f.base}
                x2={f.x}
                y2={f.base - len}
                strokeWidth={extended ? 9 : 11}
                opacity={extended ? 1 : 0.45}
                style={{ transition: "all 600ms cubic-bezier(0.16,1,0.3,1)" }}
              />
              <circle
                cx={f.x}
                cy={f.base - len}
                r={extended ? 6 : 5}
                fill="url(#hz-hand)"
                opacity={extended ? 1 : 0.4}
                style={{ transition: "all 600ms cubic-bezier(0.16,1,0.3,1)" }}
              />
            </g>
          );
        })}
        {/* tracking mesh */}
        <path
          d="M62 168 L84 150 L112 145 L140 150 L164 168"
          strokeWidth="2"
          opacity="0.5"
          className="animate-dash"
        />
      </g>

      <circle
        cx="114"
        cy="193"
        r="58"
        fill="none"
        stroke="var(--cyan)"
        strokeWidth="1"
        opacity="0.35"
        className="animate-pulse-ring"
        style={{ transformOrigin: "114px 193px" }}
      />
    </svg>
  );
}