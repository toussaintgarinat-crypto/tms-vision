from tms_vision.rula.tables import lookup_table_a, lookup_table_b, lookup_table_c


def test_table_a_worked_example_from_cornell_worksheet():
    # Upper arm=3, lower arm=2, wrist=4, wrist twist=2 -> Posture Score A = 5
    assert lookup_table_a(upper_arm=3, lower_arm=2, wrist=4, wrist_twist=2) == 5


def test_table_a_first_cell_is_minimum_score():
    assert lookup_table_a(upper_arm=1, lower_arm=1, wrist=1, wrist_twist=1) == 1


def test_table_a_last_cell_is_maximum_score():
    assert lookup_table_a(upper_arm=6, lower_arm=3, wrist=4, wrist_twist=2) == 9


def test_table_b_worked_example_from_cornell_worksheet():
    # Neck=3, trunk=2, legs=1 -> Posture Score B = 3
    assert lookup_table_b(neck=3, trunk=2, legs=1) == 3


def test_table_b_first_cell_is_minimum_score():
    assert lookup_table_b(neck=1, trunk=1, legs=1) == 1


def test_table_c_worked_example_from_cornell_worksheet():
    # Wrist & Arm Score=7, Neck/Trunk/Leg Score=5 -> Final RULA Score = 7
    assert lookup_table_c(wrist_arm_score=7, neck_trunk_leg_score=5) == 7


def test_table_c_clamps_scores_above_the_table_bounds():
    # Table C only goes up to row "8+" and column "7+"; scores above that
    # (possible once muscle use + force/load are added) must clamp, not crash.
    assert lookup_table_c(wrist_arm_score=13, neck_trunk_leg_score=11) == 7


def test_table_a_clamps_out_of_range_inputs():
    assert lookup_table_a(upper_arm=9, lower_arm=1, wrist=1, wrist_twist=1) == lookup_table_a(
        upper_arm=6, lower_arm=1, wrist=1, wrist_twist=1
    )
