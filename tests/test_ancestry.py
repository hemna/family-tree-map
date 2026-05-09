from app.ancestry import compute_relationship_label


def test_gen1_father():
    assert compute_relationship_label(1, "Male", "paternal") == "paternal father"


def test_gen1_mother():
    assert compute_relationship_label(1, "Female", "maternal") == "maternal mother"


def test_gen2_grandfather():
    assert compute_relationship_label(2, "Male", "paternal") == "paternal grandfather"


def test_gen2_grandmother():
    assert compute_relationship_label(2, "Female", "maternal") == "maternal grandmother"


def test_gen3_great_grandfather():
    assert compute_relationship_label(3, "Male", "paternal") == "paternal great-grandfather"


def test_gen3_great_grandmother():
    assert compute_relationship_label(3, "Female", "paternal") == "paternal great-grandmother"


def test_gen4():
    assert compute_relationship_label(4, "Male", "maternal") == "maternal 2nd great-grandfather"


def test_gen5():
    assert compute_relationship_label(5, "Female", "paternal") == "paternal 3rd great-grandmother"


def test_gen6():
    assert compute_relationship_label(6, "Male", "maternal") == "maternal 4th great-grandfather"
