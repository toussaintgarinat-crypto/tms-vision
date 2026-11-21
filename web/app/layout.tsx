import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { AuthProvider } from "./auth/AuthProvider";
import { I18nProvider } from "./i18n/I18nProvider";
import { NavMenu } from "./NavMenu";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TMS Vision — Vérification RULA",
  description:
    "Enregistrez un court clip caméra pour obtenir une évaluation RULA (score ergonomique) instantanée.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="fr"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <I18nProvider>
          <AuthProvider>
            <NavMenu />
            {children}
          </AuthProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
