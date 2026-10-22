import { describe, expect, it } from "vitest";

import { pickVideoFile } from "./videoDrop";

const file = (name: string, type: string, content = "x") => new File([content], name, { type });

describe("pickVideoFile", () => {
  it("takes the first video among the files", () => {
    const picked = pickVideoFile([file("a.txt", "text/plain"), file("b.mp4", "video/mp4")]);
    expect(picked.file?.name).toBe("b.mp4");
  });

  it("accepts a known video extension when the browser gives no type", () => {
    expect(pickVideoFile([file("clip.MOV", "")]).file?.name).toBe("clip.MOV");
  });

  it("refuses non-video files, empty files and nothing at all", () => {
    expect(pickVideoFile([file("photo.png", "image/png")]).error).toBe("Ce fichier n'est pas une vidéo.");
    expect(pickVideoFile([file("v.mp4", "video/mp4", "")]).error).toBe("Le fichier sélectionné est vide.");
    expect(pickVideoFile([]).error).toBe("Aucun fichier reçu.");
    expect(pickVideoFile(null).error).toBe("Aucun fichier reçu.");
  });
});
