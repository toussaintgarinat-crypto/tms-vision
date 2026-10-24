// Démo par métier : la fiche de poste, les zones sollicitées et le programme de micro-pauses,
// avec la possibilité de copier une fiche pour l'adapter à une personne. La démo est une page
// autonome (web/public/demo-metiers.html) affichée ici pour garder le menu de l'application.
export const metadata = {
  title: "Démo par métier — TMS Vision",
};

export default function DemoPage() {
  return (
    <iframe
      src="/demo-metiers.html"
      title="Démo par métier"
      className="w-full flex-1 border-0"
      style={{ minHeight: "calc(100vh - 3.5rem)" }}
    />
  );
}
