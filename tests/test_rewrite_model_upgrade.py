import push_to_talk_realtime as app
from usage_tracking import estimate


def test_upgrade_preserves_instructions_and_transcription():
    original = {
        "transcription_model": "gpt-transcribe",
        "rewrite_profiles": {
            "tidy": {"model": "gpt-5.6-terra", "instructions": "Keep names."},
            "fun": {"model": "gpt-5.6-luna", "instructions": "Be upbeat."},
        },
    }
    upgraded = app.migrate_rewrite_models(original)
    assert upgraded["post_process_model"] == "gpt-6.1-sol"
    assert upgraded["rewrite_profiles"]["tidy"] == {
        "model": "gpt-6.1-sol",
        "instructions": "Keep names.",
    }
    assert upgraded["transcription_model"] == "gpt-transcribe"
    assert original["rewrite_profiles"]["tidy"]["model"] == "gpt-5.6-terra"
    upgraded["rewrite_profiles"]["tidy"]["model"] = "gpt-5.6-luna"
    assert app.migrate_rewrite_models(upgraded) == upgraded


def test_sol_cost():
    assert (
        estimate(
            "gpt-6.1-sol",
            0,
            {
                "input_tokens": 1000,
                "output_tokens": 100,
                "input_tokens_details": {"cached_tokens": 500},
            },
            True,
        )[0]
        == 2050000
    )
