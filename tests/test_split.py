from app.split import split_customer_name


def test_names_at_or_under_100_are_untouched():
    name = "Müller & Söhne GmbH"
    r = split_customer_name(name)
    assert (r.part1, r.part2, r.was_split) == (name, "", False)
    assert split_customer_name("a" * 100).was_split is False


def test_splits_on_last_space_never_mid_word():
    name = (
        "Zweckverband Gemeinschaftliche Wasserversorgung und Abwasserentsorgung "
        "Landkreis Oberallgäu Süd Kempten Immenstadt"
    )
    r = split_customer_name(name)
    assert r.was_split
    assert len(r.part1) <= 100
    assert f"{r.part1} {r.part2}" == name  # nothing lost, nothing added
    assert r.part1 == name[:95]
    assert r.part2 == "Kempten Immenstadt"


def test_part1_is_exactly_100_when_101st_char_is_space():
    r = split_customer_name("x" * 100 + " Teil Zwei")
    assert len(r.part1) == 100
    assert r.part2 == "Teil Zwei"


def test_falls_back_to_separator_when_no_usable_space():
    r = split_customer_name("A" * 80 + "-" + "B" * 40)
    assert r.part1 == "A" * 80 + "-"
    assert r.part2 == "B" * 40


def test_hard_cuts_single_long_token():
    r = split_customer_name("Z" * 130)
    assert (len(r.part1), len(r.part2)) == (100, 30)


def test_ignores_early_space_that_leaves_part1_nearly_empty():
    r = split_customer_name("AB " + "C" * 120)
    assert len(r.part1) == 100


def test_counts_decomposed_umlauts_as_one_char():
    assert split_customer_name("ü" * 100).was_split is False


def test_collapses_whitespace_and_strips_leading_comma_from_teil2():
    r = split_customer_name("W" * 99 + ",   Niederlassung   Nord")
    assert len(r.part1) <= 100
    assert r.part2 == "Niederlassung Nord"


def test_second_run_on_part1_is_noop_loop_safety():
    r = split_customer_name("Wort " * 40)
    assert split_customer_name(r.part1).was_split is False


def test_handles_none_and_empty():
    assert split_customer_name(None).was_split is False
    assert split_customer_name("").part1 == ""
