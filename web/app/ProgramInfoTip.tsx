import { useId, useState } from "react";

// Bulle ⓘ : explique pourquoi un exercice est proposé. S'ouvre au survol de la souris, au focus
// clavier et au clic (pour les écrans tactiles) ; Échap la ferme.
export function InfoTip({ lines }: { lines: string[] }) {
  const id = useId();
  const [hover, setHover] = useState(false);
  const [pinned, setPinned] = useState(false);
  const open = hover || pinned;

  return (
    <span
      className="relative ml-2 inline-block align-middle"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <button
        type="button"
        aria-label="Pourquoi cet exercice ?"
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setPinned((value) => !value)}
        onFocus={() => setHover(true)}
        onBlur={() => {
          setHover(false);
          setPinned(false);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setHover(false);
            setPinned(false);
          }
        }}
        className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-blue-700 text-xs font-bold italic text-blue-800"
      >
        i
      </button>
      {open && (
        <span
          id={id}
          role="tooltip"
          className="absolute left-0 top-6 z-10 flex w-72 max-w-[80vw] flex-col gap-1 rounded border border-gray-300 bg-white p-2 text-xs font-normal not-italic text-gray-900 shadow-lg"
        >
          {lines.map((line, index) => (
            <span key={index}>{line}</span>
          ))}
        </span>
      )}
    </span>
  );
}
