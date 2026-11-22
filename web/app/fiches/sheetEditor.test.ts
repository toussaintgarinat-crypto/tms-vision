import { describe, expect, it } from "vitest";
import {
  addKeyframe, addPose, canRemovePose, clampAngle, emptySheet, poseNameError, removePose, setAngle,
  sheetProblems, singlePosePreview, skeletonWarnings, toPayload, previewExercise,
} from "./sheetEditor";

function valid() {
  const sheet = emptySheet();
  sheet.title = "Étirement";
  sheet.description = "Description";
  sheet.instructions = [{ t: 0, text: "Tenez la position." }];
  return sheet;
}

describe("setAngle", () => {
  it("fixes an angle and drops it, then the bone, when it returns to zero", () => {
    let poses = setAngle(emptySheet().poses, "tenue", "neck", "lateral", 35);
    expect(poses.tenue).toEqual({ neck: { lateral: 35 } });
    poses = setAngle(poses, "tenue", "neck", "flexion", 10);
    expect(poses.tenue.neck).toEqual({ lateral: 35, flexion: 10 });
    poses = setAngle(poses, "tenue", "neck", "lateral", 0);
    poses = setAngle(poses, "tenue", "neck", "flexion", 0);
    expect(poses.tenue).toEqual({});
  });

  it("clamps to the range accepted by the server and ignores NaN", () => {
    expect(clampAngle(400)).toBe(180);
    expect(clampAngle(-400)).toBe(-180);
    expect(clampAngle(Number.NaN)).toBe(0);
    expect(setAngle({ a: {} }, "a", "head", "twist", 999).a.head).toEqual({ twist: 180 });
  });

  it("does not touch the other poses", () => {
    const poses = setAngle(emptySheet().poses, "tenue", "spine", "flexion", 20);
    expect(poses.neutral).toEqual({});
  });
});

describe("poses", () => {
  it("validates pose names", () => {
    expect(poseNameError("", [])).toBe("empty");
    expect(poseNameError("Pose 1", [])).toBe("format");
    expect(poseNameError("tenue", ["tenue"])).toBe("taken");
    expect(poseNameError("tilt_right", ["tenue"])).toBeNull();
  });

  it("copies an existing pose and refuses to delete a used or last pose", () => {
    const sheet = valid();
    sheet.poses = setAngle(sheet.poses, "tenue", "neck", "lateral", 20);
    const withCopy = addPose(sheet, "autre", "tenue");
    expect(withCopy.poses.autre).toEqual({ neck: { lateral: 20 } });
    withCopy.poses.autre.neck!.lateral = 99; // pas d'alias avec la pose copiée
    expect(sheet.poses.tenue.neck!.lateral).toBe(20);
    expect(canRemovePose(withCopy, "tenue")).toBe(false);
    expect(canRemovePose(withCopy, "autre")).toBe(true);
    expect(Object.keys(removePose(withCopy, "autre").poses)).toEqual(["neutral", "tenue"]);
    expect(removePose(withCopy, "tenue")).toBe(withCopy);
  });
});

describe("sheetProblems", () => {
  it("accepts a complete sheet", () => {
    expect(sheetProblems(valid())).toEqual([]);
  });

  it("reports the same problems as the server", () => {
    const sheet = valid();
    sheet.title = " ";
    sheet.duration_seconds = 5;
    sheet.keyframes = [{ t: 2, pose: "neutral" }, { t: 1, pose: "inconnue" }];
    sheet.instructions = [{ t: 0, text: "" }];
    const codes = sheetProblems(sheet).map((problem) => problem.code);
    expect(codes).toEqual(
      expect.arrayContaining(["title", "duration", "keyframeStart", "keyframeOrder", "keyframePose", "instructionText"]),
    );
  });

  it("flags a last keyframe past the duration and unordered instructions", () => {
    const sheet = valid();
    sheet.duration_seconds = 10;
    sheet.keyframes = [{ t: 0, pose: "neutral" }, { t: 12, pose: "tenue" }];
    sheet.instructions = [{ t: 4, text: "a" }, { t: 2, text: "b" }, { t: 30, text: "c" }];
    const codes = sheetProblems(sheet).map((problem) => problem.code);
    expect(codes).toEqual(expect.arrayContaining(["keyframeEnd", "instructionOrder", "instructionRange"]));
  });
});

describe("keyframes and previews", () => {
  it("adds a keyframe 5 s after the last one, within the duration", () => {
    const sheet = valid();
    expect(addKeyframe(sheet, "tenue").keyframes.at(-1)).toEqual({ t: 20, pose: "tenue" });
    sheet.duration_seconds = 60;
    expect(addKeyframe(sheet, "tenue").keyframes.at(-1)).toEqual({ t: 25, pose: "tenue" });
  });

  it("previews one pose held for the minimum duration", () => {
    const sheet = valid();
    sheet.poses = setAngle(sheet.poses, "tenue", "spine", "flexion", 30);
    const preview = singlePosePreview(sheet, "tenue");
    expect(preview.poses).toEqual({ tenue: { spine: { flexion: 30 } } });
    expect(preview.duration_seconds).toBe(10);
    expect(previewExercise(sheet).keyframes).toHaveLength(4);
  });

  it("omits an empty benefit from the payload", () => {
    expect("benefit" in toPayload(valid())).toBe(false);
    const sheet = { ...valid(), benefit: " Détend le cou. " };
    expect(toPayload(sheet).benefit).toBe("Détend le cou.");
  });
});

describe("skeletonWarnings", () => {
  it("signals grouped bones and extreme angles without forbidding them", () => {
    let poses = setAngle(emptySheet().poses, "tenue", "L_fingers", "flexion", 40);
    poses = setAngle(poses, "tenue", "neck", "lateral", 170);
    const sheet = { ...emptySheet(), poses };
    const warnings = skeletonWarnings(sheet);
    expect(warnings).toContainEqual({ code: "grouped", pose: "tenue", bone: "L_fingers" });
    expect(warnings).toContainEqual({ code: "extreme", pose: "tenue", bone: "neck", angle: "lateral", value: 170 });
  });

  it("has no warning on a reasonable sheet", () => {
    const poses = setAngle(emptySheet().poses, "tenue", "neck", "lateral", 35);
    expect(skeletonWarnings({ ...emptySheet(), poses })).toEqual([]);
  });
});
