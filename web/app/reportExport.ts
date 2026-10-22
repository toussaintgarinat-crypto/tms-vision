// Fichier HTML autonome du compte rendu : une seule page, styles et images inclus, qui
// s'ouvre dans n'importe quel navigateur et se transmet par mail.

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Fait avancer les carrousels (boutons ← →) sans dépendance : même rendu dans l'application et
// dans le fichier exporté.
export const CAROUSEL_SCRIPT = `document.addEventListener("click",function(e){
var b=e.target.closest("[data-dir]");if(!b)return;
var c=b.closest(".carousel");if(!c)return;
var s=c.querySelectorAll(".step");var i=0;
s.forEach(function(x,k){if(x.classList.contains("active"))i=k;});
var n=(i+Number(b.getAttribute("data-dir"))+s.length)%s.length;
s.forEach(function(x,k){x.classList.toggle("active",k===n);});
var t=c.querySelector(".count");if(t)t.textContent=(n+1)+" / "+s.length;});`;

export function buildStandaloneHtml(title: string, bodyHtml: string): string {
  return `<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(title)}</title>
</head>
<body style="margin:0;background:#fff">
${bodyHtml}
<script>${CAROUSEL_SCRIPT}</script>
</body>
</html>
`;
}

export function reportFileName(kind: "carousel" | "video", date: Date): string {
  const day = date.toISOString().slice(0, 10);
  return `compte-rendu-${kind === "video" ? "videos" : "carrousels"}-${day}.html`;
}

export async function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}
