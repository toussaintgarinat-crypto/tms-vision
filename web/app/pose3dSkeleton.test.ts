import { describe, expect, it } from "vitest";
import { BONE_ORDER, buildSkeleton } from "./pose3dSkeleton";

describe("buildSkeleton", () => {
  it("crée 9 os (racine + 8) avec la hiérarchie attendue", () => {
    const { skeleton, bones } = buildSkeleton();

    expect(BONE_ORDER.length).toBe(9);
    expect(skeleton.bones.length).toBe(9);

    expect(bones.root.parent).toBeNull();
    expect(bones.spine.parent).toBe(bones.root);
    expect(bones.neck.parent).toBe(bones.spine);
    expect(bones.L_upper_arm.parent).toBe(bones.spine);
    expect(bones.L_forearm.parent).toBe(bones.L_upper_arm);
    expect(bones.R_upper_arm.parent).toBe(bones.spine);
    expect(bones.R_forearm.parent).toBe(bones.R_upper_arm);
    expect(bones.L_thigh.parent).toBe(bones.root);
    expect(bones.R_thigh.parent).toBe(bones.root);
  });
});
