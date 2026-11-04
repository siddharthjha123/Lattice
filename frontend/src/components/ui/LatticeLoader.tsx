"use client";

import { useEffect, useRef, useState } from "react";

export type LatticeLoaderProps = {
  /** Width and height in px */
  size?: number;
  /** true = keep looping, false = finish: every node turns active and the logo completes */
  loading?: boolean;
  /** Time each node stays lit, in ms */
  stepMs?: number;
  baseColor?: string;
  activeColor?: string;
  /** Called once the logo is complete */
  onComplete?: () => void;
  className?: string;
};

type Pt = [number, number];

// Clockwise from the top vertex
const V: Pt[] = [
  [60, 8],
  [105, 34],
  [105, 86],
  [60, 112],
  [15, 86],
  [15, 34],
];
const C: Pt = [60, 60];
const mid = (a: Pt, b: Pt): Pt => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];

export default function LatticeLoader({
  size = 120,
  loading = true,
  stepMs = 700,
  baseColor = "#72B0AB",
  activeColor = "#BCDDDC",
  onComplete,
  className,
}: LatticeLoaderProps) {
  const [active, setActive] = useState(0);
  const [filled, setFilled] = useState<boolean[]>(Array(6).fill(false));
  const [done, setDone] = useState(false);

  const activeRef = useRef(active);
  activeRef.current = active;
  const doneRef = useRef(onComplete);
  doneRef.current = onComplete;

  useEffect(() => {
    // Loop: one node lights up at a time, moving clockwise
    if (loading) {
      setFilled(Array(6).fill(false));
      setDone(false);
      const t = setInterval(() => setActive((a) => (a + 1) % 6), stepMs);
      return () => clearInterval(t);
    }

    // Finish: keep each node green as the sweep passes it
    const start = activeRef.current < 0 ? 0 : activeRef.current;
    let n = 1;
    let end: ReturnType<typeof setTimeout>;
    setFilled((f) => f.map((v, i) => v || i === start));
    setActive(-1);
    const t = setInterval(() => {
      const idx = (start + n) % 6;
      setFilled((f) => f.map((v, i) => v || i === idx));
      n++;
      if (n >= 6) {
        clearInterval(t);
        end = setTimeout(() => {
          setDone(true);
          doneRef.current?.();
        }, stepMs);
      }
    }, stepMs);
    return () => {
      clearInterval(t);
      clearTimeout(end);
    };
  }, [loading, stepMs]);

  const on = (i: number) => active === i || filled[i];
  const t = `${Math.round(stepMs * 0.7)}ms`;

  return (
    <>
      <style>{`@media (prefers-reduced-motion: reduce){.lattice-loader *{transition:none!important}}`}</style>
      <svg
        className={`lattice-loader ${className ?? ""}`}
        viewBox="0 0 120 120"
        width={size}
        height={size}
        role="status"
        aria-label={done ? "Loaded" : "Loading"}
        style={{ overflow: "visible" }}
      >
        {/* Base edges */}
        <g
          stroke={baseColor}
          strokeWidth={4}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        >
          <polygon points={V.map((p) => p.join(",")).join(" ")} />
          {V.map((p, i) => (
            <line key={i} x1={p[0]} y1={p[1]} x2={C[0]} y2={C[1]} />
          ))}
        </g>

        {/* Active edges grow out of each lit node: spoke to the centre, half of each side edge */}
        <g
          stroke={activeColor}
          strokeWidth={4}
          strokeLinecap="round"
          fill="none"
        >
          {V.map((p, i) =>
            [C, mid(p, V[(i + 1) % 6]), mid(p, V[(i + 5) % 6])].map((q, j) => (
              <line
                key={`${i}-${j}`}
                x1={p[0]}
                y1={p[1]}
                x2={q[0]}
                y2={q[1]}
                pathLength={1}
                strokeDasharray="1 1"
                strokeDashoffset={on(i) ? 0 : 1}
                style={{ transition: `stroke-dashoffset ${t} ease-in-out` }}
              />
            ))
          )}
        </g>

        {/* Vertex nodes */}
        {V.map((p, i) => (
          <circle
            key={i}
            cx={p[0]}
            cy={p[1]}
            r={7}
            fill={on(i) ? activeColor : baseColor}
            style={{
              transition: "fill 300ms ease, filter 300ms ease",
              filter:
                active === i ? `drop-shadow(0 0 5px ${activeColor})` : "none",
            }}
          />
        ))}

        {/* Centre node */}
        <circle
          cx={C[0]}
          cy={C[1]}
          r={12}
          fill={activeColor}
          style={{
            transformOrigin: "60px 60px",
            transform: done ? "scale(1.12)" : "scale(1)",
            transition: "transform 400ms ease",
          }}
        />
      </svg>
    </>
  );
}

export { LatticeLoader };
