import { describe, expect, it } from "vitest";

import {
  DEFAULT_POSE_SETTINGS,
  MAX_CUSTOM_POINTS,
  PoseSettings,
  applyChoice,
  clickToNormalized,
  defaultPointName,
  expectedKeypointCount,
  groupsForOptions,
  poseFormFields,
  poseModelLabel,
  validatePoseSettings,
} from "./poseModels";

const withPoints = (settings: PoseSettings, n: number): PoseSettings => ({
  ...settings,
  customPoints: Array.from({ length: n }, (_, i) => ({ name: `p${i}`, x: 0.1 * (i + 1), y: 0.5 })),
});

describe("réglages par défaut", () => {
  it("envoient exactement l'analyse historique : MediaPipe Pose 33, rien d'autre", () => {
    expect(poseFormFields(DEFAULT_POSE_SETTINGS)).toEqual({
      pose_model: "mediapipe_pose_33",
      enable_wholebody: "false",
      enable_hands: "false",
      enable_feet: "false",
      enable_face: "false",
      custom_points: "false",
    });
    expect(expectedKeypointCount(DEFAULT_POSE_SETTINGS)).toBe(33);
    expect(validatePoseSettings(DEFAULT_POSE_SETTINGS)).toBeNull();
  });
});

describe("applyChoice", () => {
  it("Pose + Hands active les mains", () => {
    const s = applyChoice(DEFAULT_POSE_SETTINGS, "mediapipe_pose_hands");
    expect(poseFormFields(s).enable_hands).toBe("true");
    expect(expectedKeypointCount(s)).toBe(75);
  });

  it("Whole-body active mains et pieds, pas le visage, et change de modèle", () => {
    const s = applyChoice(DEFAULT_POSE_SETTINGS, "rtmpose_wholebody");
    const fields = poseFormFields(s);
    expect(fields).toMatchObject({
      pose_model: "rtmpose_wholebody_133",
      enable_wholebody: "true",
      enable_hands: "true",
      enable_feet: "true",
      enable_face: "false",
    });
    expect(expectedKeypointCount(s)).toBe(17 + 42 + 6);
    expect(expectedKeypointCount({ ...s, face: true })).toBe(17 + 42 + 6 + 68);
  });

  it("revenir à Pose 33 coupe mains, pieds, visage et points personnalisés", () => {
    let s = applyChoice(DEFAULT_POSE_SETTINGS, "rtmpose_wholebody");
    s = { ...s, face: true, customEnabled: true };
    s = applyChoice(s, "mediapipe_pose_33");
    expect(s).toMatchObject({ hands: false, feet: false, face: false, customEnabled: false });
  });

  it("Custom keypoints active les points personnalisés et garde le choix des mains", () => {
    const s = applyChoice({ ...DEFAULT_POSE_SETTINGS, hands: true }, "custom_keypoints");
    expect(s.customEnabled).toBe(true);
    expect(s.hands).toBe(true);
  });

  it("n'envoie pieds et visage qu'avec le whole-body, même si les cases restent cochées", () => {
    const s: PoseSettings = { ...DEFAULT_POSE_SETTINGS, feet: true, face: true };
    expect(poseFormFields(s)).toMatchObject({ enable_feet: "false", enable_face: "false" });
    expect(expectedKeypointCount(s)).toBe(33);
  });
});

describe("points personnalisés", () => {
  it("sont envoyés avec l'instant de référence, sans autre champ", () => {
    const s = withPoints({ ...applyChoice(DEFAULT_POSE_SETTINGS, "custom_keypoints"), customReferenceTime: 1.25 }, 2);
    const fields = poseFormFields(s);
    expect(fields.custom_points).toBe("true");
    expect(JSON.parse(fields.custom_points_json)).toEqual({
      reference_time_seconds: 1.25,
      points: [
        { name: "p0", x: 0.1, y: 0.5 },
        { name: "p1", x: 0.2, y: 0.5 },
      ],
    });
    expect(expectedKeypointCount(s)).toBe(35);
  });

  it("ne sont pas envoyés quand l'option est décochée, même s'il en reste dans l'éditeur", () => {
    const s = withPoints(DEFAULT_POSE_SETTINGS, 3);
    expect(poseFormFields(s).custom_points_json).toBeUndefined();
    expect(expectedKeypointCount(s)).toBe(33);
  });

  it("l'option cochée sans point est refusée avant l'envoi", () => {
    const s = applyChoice(DEFAULT_POSE_SETTINGS, "custom_keypoints");
    expect(validatePoseSettings(s)).toMatch(/au moins un point/);
    expect(validatePoseSettings(withPoints(s, 1))).toBeNull();
    expect(validatePoseSettings(withPoints(s, MAX_CUSTOM_POINTS + 1))).toMatch(/Au plus/);
  });

  it("noms par défaut sans doublon", () => {
    expect(defaultPointName([])).toBe("point 1");
    expect(defaultPointName([{ name: "point 2", x: 0, y: 0 }])).toBe("point 3");
    expect(defaultPointName([{ name: "Point 2", x: 0, y: 0 }, { name: "x", x: 0, y: 0 }])).toBe("point 3");
  });
});

describe("clickToNormalized", () => {
  const rect = { left: 100, top: 50, width: 400, height: 200 };

  it("convertit un clic en coordonnées de l'image", () => {
    expect(clickToNormalized(300, 150, rect)).toEqual({ x: 0.5, y: 0.5 });
    expect(clickToNormalized(100, 50, rect)).toEqual({ x: 0, y: 0 });
    expect(clickToNormalized(500, 250, rect)).toEqual({ x: 1, y: 1 });
  });

  it("refuse un clic hors de l'image ou une image sans taille", () => {
    expect(clickToNormalized(99, 100, rect)).toBeNull();
    expect(clickToNormalized(300, 251, rect)).toBeNull();
    expect(clickToNormalized(10, 10, { left: 0, top: 0, width: 0, height: 0 })).toBeNull();
  });
});

describe("légende et libellés", () => {
  it("liste les groupes présents d'après les options enregistrées", () => {
    expect(groupsForOptions(undefined)).toEqual(["body"]);
    expect(groupsForOptions({ enable_hands: true, custom_points: true })).toEqual(["body", "hands", "custom"]);
    expect(
      groupsForOptions({ pose_model: "rtmpose_wholebody_133", enable_hands: true, enable_feet: true, enable_face: true }),
    ).toEqual(["body", "hands", "feet", "face"]);
    // pieds et visage n'existent qu'en whole-body
    expect(groupsForOptions({ enable_feet: true, enable_face: true })).toEqual(["body"]);
  });

  it("nomme le modèle, y compris pour une ancienne analyse sans modèle", () => {
    expect(poseModelLabel("rtmpose_wholebody_133")).toBe("RTMPose Whole-body");
    expect(poseModelLabel(null)).toBe("MediaPipe Pose 33");
  });
});
