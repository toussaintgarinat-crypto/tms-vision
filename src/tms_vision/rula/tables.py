"""Tables de scoring RULA officielles (Tables A, B, C).

Source : RULA Employee Assessment Worksheet, Prof. Alan Hedge, Cornell
University (Feb. 2001), citant McAtamney, L. & Corlett, E.N. (1993),
"RULA: a survey method for the investigation of work-related upper limb
disorders", Applied Ergonomics, 24(2), 91-99.

Chaque valeur a été vérifiée contre l'exemple travaillé du document source :
upper_arm=3, lower_arm=2, wrist=4, wrist_twist=2 -> Table A = 5
neck=3, trunk=2, legs=1 -> Table B = 3
wrist_arm_score=7, neck_trunk_leg_score=5 -> Table C = 7
"""

# TABLE_A[upper_arm-1][lower_arm-1] = [[wrist1_twist1, wrist1_twist2],
#                                       [wrist2_twist1, wrist2_twist2],
#                                       [wrist3_twist1, wrist3_twist2],
#                                       [wrist4_twist1, wrist4_twist2]]
TABLE_A = [
    [  # upper_arm = 1
        [[1, 2], [2, 2], [2, 3], [3, 3]],  # lower_arm = 1
        [[2, 2], [2, 2], [3, 3], [3, 3]],  # lower_arm = 2
        [[2, 3], [2, 3], [3, 3], [4, 4]],  # lower_arm = 3
    ],
    [  # upper_arm = 2
        [[2, 2], [2, 3], [3, 3], [4, 4]],  # lower_arm = 1
        [[2, 2], [2, 3], [3, 3], [4, 4]],  # lower_arm = 2
        [[2, 3], [3, 3], [3, 4], [4, 5]],  # lower_arm = 3
    ],
    [  # upper_am = 3
        [[2, 3], [3, 3], [4, 4], [5, 5]],  # lower_arm = 1
        [[2, 3], [3, 3], [4, 4], [5, 5]],  # lower_arm = 2
        [[2, 3], [3, 4], [4, 4], [5, 5]],  # lower_arm = 3
    ],
    [  # upper_arm = 4
        [[3, 4], [4, 4], [4, 4], [5, 5]],  # lower_arm = 1
        [[3, 4], [4, 4], [4, 4], [5, 5]],  # lower_arm = 2
        [[3, 4], [4, 5], [5, 5], [6, 6]],  # lower_arm = 3
    ],
    [  # upper_arm = 5
        [[5, 5], [5, 5], [5, 6], [6, 7]],  # lower_arm = 1
        [[5, 6], [6, 6], [6, 7], [7, 7]],  # lower_arm = 2
        [[6, 6], [6, 7], [7, 7], [7, 8]],  # lower_arm = 3
    ],
    [  # upper_arm = 6
        [[7, 7], [7, 7], [7, 8], [8, 9]],  # lower_arm = 1
        [[7, 8], [8, 8], [8, 9], [9, 9]],  # lower_arm = 2
        [[9, 9], [9, 9], [9, 9], [9, 9]],  # lower_arm = 3
    ],
]

# TABLE_B[neck-1][trunk-1] = [legs1, legs2]
TABLE_B = [
    [[1, 3], [2, 3], [3, 4], [5, 5], [6, 6], [7, 7]],  # neck = 1
    [[2, 3], [2, 3], [4, 5], [5, 5], [6, 7], [7, 7]],  # neck = 2
    [[3, 3], [3, 4], [4, 5], [5, 6], [6, 7], [7, 7]],  # neck = 3
    [[5, 5], [5, 6], [6, 7], [7, 7], [7, 7], [8, 8]],  # neck = 4
    [[7, 7], [7, 7], [7, 8], [8, 8], [8, 8], [8, 8]],  # neck = 5
    [[8, 8], [8, 8], [8, 8], [8, 9], [9, 9], [9, 9]],  # neck = 6
]

# TABLE_C[wrist_arm_score-1][neck_trunk_leg_score-1], row/col 8 = "8+"/"7+"
TABLE_C = [
    [1, 2, 3, 3, 4, 5, 5],  # wrist_arm_score = 1
    [2, 2, 3, 4, 4, 5, 5],  # wrist_arm_score = 2
    [3, 3, 3, 4, 4, 5, 6],  # wrist_arm_score = 3
    [3, 3, 3, 4, 5, 6, 6],  # wrist_arm_score = 4
    [4, 4, 4, 5, 6, 7, 7],  # wrist_arm_score = 5
    [4, 4, 5, 6, 6, 7, 7],  # wrist_arm_score = 6
    [5, 5, 6, 6, 7, 7, 7],  # wrist_arm_score = 7
    [5, 5, 6, 7, 7, 7, 7],  # wrist_arm_score = 8+
]


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(value, high))


def lookup_table_a(upper_arm: int, lower_arm: int, wrist: int, wrist_twist: int) -> int:
    ua = _clamp(upper_arm, 1, 6) - 1
    la = _clamp(lower_arm, 1, 3) - 1
    w = _clamp(wrist, 1, 4) - 1
    twist = _clamp(wrist_twist, 1, 2) - 1
    return TABLE_A[ua][la][w][twist]


def lookup_table_b(neck: int, trunk: int, legs: int) -> int:
    n = _clamp(neck, 1, 6) - 1
    t = _clamp(trunk, 1, 6) - 1
    legs_index = _clamp(legs, 1, 2) - 1
    return TABLE_B[n][t][legs_index]


def lookup_table_c(wrist_arm_score: int, neck_trunk_leg_score: int) -> int:
    row = _clamp(wrist_arm_score, 1, 8) - 1
    col = _clamp(neck_trunk_leg_score, 1, 7) - 1
    return TABLE_C[row][col]
