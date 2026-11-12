// Tabby: a little spreadsheet shaped like a speech bubble.
// mood: "idle" | "thinking" | "happy" | "oops"

const BODY =
  "M12 6h48a8 8 0 0 1 8 8v36a8 8 0 0 1-8 8H30l-12 10v-10h-6a8 8 0 0 1-8-8V14a8 8 0 0 1 8-8z";

export default function Mascot({ mood = "idle", size = 64, className = "" }) {
  const look = mood === "thinking" ? { x: 2, y: -2 } : mood === "oops" ? { x: 0, y: 1 } : { x: 0, y: 0 };

  return (
    <svg
      className={`mascot mascot--${mood} ${className}`}
      width={size}
      height={size}
      viewBox="0 0 72 72"
      aria-hidden="true"
    >
      <path d={BODY} fill="var(--grape)" />
      {/* header row, like a spreadsheet's column headers */}
      <path d="M12 6h48a8 8 0 0 1 8 8v6H4v-6a8 8 0 0 1 8-8z" fill="var(--sunny)" />
      <g stroke="var(--ink)" strokeWidth="2">
        <line x1="4" y1="20" x2="68" y2="20" />
        <line x1="26" y1="6" x2="26" y2="20" />
        <line x1="46" y1="6" x2="46" y2="20" />
      </g>
      <path d={BODY} fill="none" stroke="var(--ink)" strokeWidth="3" strokeLinejoin="round" />

      <g className="mascot__eyes">
        <ellipse cx="27" cy="34" rx="6" ry="6.5" fill="white" />
        <ellipse cx="45" cy="34" rx="6" ry="6.5" fill="white" />
        <circle cx={27 + look.x} cy={35 + look.y} r="3" fill="var(--ink)" />
        <circle cx={45 + look.x} cy={35 + look.y} r="3" fill="var(--ink)" />
      </g>

      {mood === "happy" && (
        <path d="M29 44q7 8 14 0" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" />
      )}
      {mood === "idle" && (
        <path d="M31 45q5 4 10 0" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" />
      )}
      {mood === "thinking" && <circle cx="36" cy="46" r="2.5" fill="white" />}
      {mood === "oops" && (
        <path d="M31 48q5 -4 10 0" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" />
      )}
    </svg>
  );
}
