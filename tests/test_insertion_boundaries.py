import pytest

from insertion_formatting import CaretContext, choose_plan, format_insertion


@pytest.mark.parametrize(
    "before,after,text,replacing,wanted",
    [
        ("\u200d", "\n", "This works.", False, "This works. "),
        ("\x00", "", "That works.", False, "That works. "),
        ("a\u200db", "", "That works.", False, " that works. "),
        ("  - ", "", "This works.", False, "This works. "),
        ("  2) ", "", "This works.", False, "This works. "),
        ("Use ", " here", '"Better words."', True, '"better words"'),
        ("Use ", " here", '"Dr."', False, '"Dr."'),
        ("She said.", "", '"That works."', False, ' "That works." '),
        ("Finished!}", "", "This works.", False, " This works. "),
        ("Change ", " here", "!", False, ""),
    ],
)
def test_auto_boundaries(before, after, text, replacing, wanted):
    plan = choose_plan("auto", CaretContext(before, after, selected_lowercase_word=replacing))
    assert format_insertion(text, plan, text + " ") == wanted
