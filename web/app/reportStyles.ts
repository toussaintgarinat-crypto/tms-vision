// Styles du compte rendu (HTML simple, sans Tailwind) : les mêmes dans l'application et dans le
// fichier HTML exporté. Toujours clair, même si l'application est en mode sombre. À l'impression
// (PDF), les carrousels s'affichent en grille d'images, car une vidéo ne se lit pas sur papier.
export const REPORT_CSS = `
.tms-report{background:#fff;color:#111827;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;
  line-height:1.45;max-width:880px;margin:0 auto;padding:24px}
.tms-report h1{font-size:24px;margin:0 0 4px}
.tms-report h2{font-size:19px;margin:28px 0 8px;border-bottom:1px solid #d1d5db;padding-bottom:4px}
.tms-report h3{font-size:16px;margin:16px 0 4px}
.tms-report h2,.tms-report h3{break-after:avoid}
.tms-report p{margin:4px 0}
.tms-report .muted{color:#4b5563;font-size:13px}
.tms-report .warn{background:#fef3c7;border:1px solid #f59e0b;color:#78350f;padding:8px 12px;border-radius:6px;margin:8px 0;font-size:14px}
.tms-report table{width:100%;border-collapse:collapse;font-size:14px;margin:8px 0}
.tms-report th,.tms-report td{text-align:left;padding:6px 8px;border-bottom:1px solid #e5e7eb}
.tms-report .badge{display:inline-block;background:#fde68a;color:#78350f;font-size:12px;font-weight:600;border-radius:4px;padding:1px 8px;margin-left:6px}
.tms-report .badge.pos{background:#e0f2fe;color:#0c4a6e}
.tms-report .ex{border:1px solid #d1d5db;border-radius:8px;padding:12px;margin:12px 0;break-inside:avoid-page}
.tms-report .ex h3{margin-top:0}
.tms-report .carousel .step{display:none}
.tms-report .carousel .step.active{display:block}
.tms-report .carousel img{width:100%;max-width:420px;border-radius:6px;background:#eef1f4;display:block}
.tms-report .carousel .nav{display:flex;gap:12px;align-items:center;margin-top:6px}
.tms-report .carousel button{border:1px solid #6b7280;background:#fff;color:#111827;border-radius:4px;padding:2px 12px;cursor:pointer}
.tms-report .video video{width:100%;max-width:420px;border-radius:6px;background:#000}
.tms-report .video,.tms-report .live{display:none}
.tms-report[data-mode=video] .video{display:block}
.tms-report[data-mode=video] .stills:not(.force){display:none}
.tms-report[data-mode=animation] .live{display:block}
.tms-report[data-mode=animation] .stills{display:none}
.tms-report footer{margin-top:28px;border-top:1px solid #d1d5db;padding-top:8px}
@media print{
  .tms-report{padding:0;max-width:none}
  .tms-report .stills,.tms-report[data-mode=video] .stills:not(.force),.tms-report[data-mode=animation] .stills{display:block!important}
  .tms-report .carousel{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
  .tms-report .carousel .step,.tms-report .carousel .step.active{display:block!important;break-inside:avoid}
  .tms-report .carousel .nav,.tms-report .video,.tms-report .live{display:none!important}
}
`;
