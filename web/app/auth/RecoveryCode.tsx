"use client";

import { useI18n } from "../i18n/I18nProvider";

// Code de récupération montré UNE SEULE fois (application de bureau) : il remplace l'email pour
// retrouver un mot de passe perdu. On ne peut pas le relire ensuite, seulement en demander un nouveau.
export function RecoveryCode({ code, onDone }: { code: string; onDone: () => void }) {
  const { t } = useI18n();
  return (
    <div className="flex flex-col gap-3 rounded border border-amber-400 bg-amber-50 p-4 text-amber-950">
      <h2 className="font-semibold">{t("recovery.title")}</h2>
      <p className="text-sm">{t("recovery.help")}</p>
      <p
        className="select-all rounded bg-white px-3 py-2 text-center font-mono text-xl tracking-widest"
        aria-label={t("recovery.title")}
      >
        {code}
      </p>
      <div className="flex flex-wrap gap-3">
        <button type="button" onClick={() => void navigator.clipboard?.writeText(code).catch(() => {})} className="rounded border border-amber-700 px-3 py-1 text-sm">
          {t("recovery.copy")}
        </button>
        <button type="button" onClick={onDone} className="rounded border border-black bg-white px-3 py-1 text-sm font-semibold">
          {t("recovery.done")}
        </button>
      </div>
    </div>
  );
}
