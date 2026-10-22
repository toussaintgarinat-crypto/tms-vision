import { describe, expect, it } from "vitest";

import { CAROUSEL_SCRIPT, buildStandaloneHtml, escapeHtml, reportFileName } from "./reportExport";

describe("escapeHtml", () => {
  it("escapes markup characters", () => {
    expect(escapeHtml(`<b a="1">&</b>`)).toBe("&lt;b a=&quot;1&quot;&gt;&amp;&lt;/b&gt;");
  });
});

describe("buildStandaloneHtml", () => {
  it("wraps the report in a complete page with the carousel script and an escaped title", () => {
    const html = buildStandaloneHtml("Bilan <1>", "<main>corps</main>");
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain("<title>Bilan &lt;1&gt;</title>");
    expect(html).toContain("<main>corps</main>");
    expect(html).toContain(CAROUSEL_SCRIPT);
    expect(html).toContain('<meta charset="utf-8">');
  });
});

describe("reportFileName", () => {
  it("names the file after its content and the day", () => {
    const date = new Date("2026-10-22T10:00:00Z");
    expect(reportFileName("carousel", date)).toBe("compte-rendu-carrousels-2026-10-22.html");
    expect(reportFileName("video", date)).toBe("compte-rendu-videos-2026-10-22.html");
  });
});
