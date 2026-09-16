import { describe, expect, it } from "vitest";
import * as THREE from "three";
import { BONE_ORDER } from "./pose3dSkeleton";
import { buildTestSkinnedGeometry } from "./testSkinnedGeometry";

describe("buildTestSkinnedGeometry", () => {
  it("assigne un poids de peau de 1 sur un seul os, pour chaque vertex", () => {
    const geometry = buildTestSkinnedGeometry();
    const skinWeight = geometry.attributes.skinWeight;
    const skinIndex = geometry.attributes.skinIndex;

    expect(skinWeight.count).toBeGreaterThan(0);
    for (let i = 0; i < skinWeight.count; i++) {
      expect(skinWeight.getX(i)).toBe(1);
      expect(skinWeight.getY(i)).toBe(0);
      expect(skinWeight.getZ(i)).toBe(0);
      expect(skinWeight.getW(i)).toBe(0);
      expect(skinIndex.getX(i)).toBeGreaterThanOrEqual(0);
      expect(skinIndex.getX(i)).toBeLessThan(BONE_ORDER.length);
    }
  });

  it("produit une géométrie indexée non vide", () => {
    const geometry = buildTestSkinnedGeometry();
    expect(geometry.attributes.position.count).toBeGreaterThan(0);
    expect(geometry.index).not.toBeNull();
    expect((geometry.index as THREE.BufferAttribute).count).toBeGreaterThan(0);
  });
});
