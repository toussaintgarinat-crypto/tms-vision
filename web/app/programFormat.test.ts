import { describe, expect, it } from "vitest";

import { capsuleVideoSrc } from "./programFormat";

describe("capsuleVideoSrc", () => {
  it("construit l'adresse complète quand la vidéo existe", () => {
    expect(
      capsuleVideoSrc(
        { video_url: "/capsules/trunk-lumbar-mobility/video", video_available: true },
        "http://localhost:8000",
      ),
    ).toBe("http://localhost:8000/capsules/trunk-lumbar-mobility/video");
  });

  it("renvoie null tant que la vidéo n'est pas générée", () => {
    expect(
      capsuleVideoSrc({ video_url: "/capsules/x/video", video_available: false }, "http://api"),
    ).toBeNull();
  });

  it("renvoie null quand l'API ne précise pas la disponibilité (ancienne réponse)", () => {
    expect(capsuleVideoSrc({ video_url: "/capsules/x/video" }, "http://api")).toBeNull();
  });
});
