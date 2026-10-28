from sqlalchemy.orm import Session

from app.engine.checkers.channel import ChannelChecker
from app.engine.checkers.disclaimer import DisclaimerChecker
from app.engine.checkers.readability import ReadabilityChecker
from app.engine.checkers.style import StyleChecker
from app.engine.checkers.terminology import TerminologyChecker
from tests.engine_helpers import LINKEDIN_SAMPLE, check, context

# --- Terminology -----------------------------------------------------------------------


def test_misspelt_product_name_in_linkedin_sample(session: Session) -> None:
    findings = check(TerminologyChecker(), LINKEDIN_SAMPLE, context(session))
    assert len(findings) == 1
    f = findings[0]
    assert (f.rule.id, f.text, f.severity) == ("TRM-02", "Paywise", "minor")
    assert f.suggestion and f.suggestion.text == "PayWise"
    assert f.rule.source == "brand_book.pdf#p8"


def test_correct_product_names_are_not_flagged(session: Session) -> None:
    text = "PayWise Business, PayWise Card and PayWise Pay Later all run on PayWise."
    assert check(TerminologyChecker(), text, context(session)) == []


def test_web_addresses_are_not_product_name_mistakes(session: Session) -> None:
    text = (
        "Learn more at paywise.example or https://paywise.example/merchants, "
        "or mail help@paywise.in."
    )
    assert check(TerminologyChecker(), text, context(session)) == []
    findings = check(TerminologyChecker(), "Paywise is at paywise.example.", context(session))
    assert [f.text for f in findings] == ["Paywise"]


def test_wrong_multiword_name_is_one_finding(session: Session) -> None:
    findings = check(TerminologyChecker(), "Try Paywise Business today.", context(session))
    assert [(f.text, f.suggestion.text if f.suggestion else None) for f in findings] == [
        ("Paywise Business", "PayWise Business")
    ]


def test_case_errors_and_variants(session: Session) -> None:
    text = "Use your PayWise card or Pay Wise or PAYWISE."
    found = {
        f.text: f.suggestion.text
        for f in check(TerminologyChecker(), text, context(session))
        if f.suggestion
    }
    assert found == {"PayWise card": "PayWise Card", "Pay Wise": "PayWise", "PAYWISE": "PayWise"}


def test_fuzzy_near_miss_is_caught(session: Session) -> None:
    findings = check(TerminologyChecker(), "Download PayWyse now.", context(session))
    assert [f.text for f in findings] == ["PayWyse"]
    assert findings[0].confidence < 0.97


def test_banned_and_discouraged_words(session: Session) -> None:
    text = "A cheap and hassle-free way to get an instant loan."
    findings = check(TerminologyChecker(), text, context(session))
    by_text = {f.text: f for f in findings}
    assert by_text["cheap"].severity == "major"
    assert by_text["cheap"].suggestion and by_text["cheap"].suggestion.text == "affordable"
    assert by_text["hassle-free"].severity == "minor"
    assert by_text["instant loan"].rule.id == "TRM-05"


# --- Disclaimers -----------------------------------------------------------------------


def test_missing_offer_and_pay_later_disclaimers(session: Session) -> None:
    text = "Enjoy free setup this month. Try PayWise Pay Later for up to 30 interest-free days."
    findings = {f.rule.id: f for f in check(DisclaimerChecker(), text, context(session, "email"))}
    assert set(findings) == {"DSC-01", "DSC-02"}
    assert findings["DSC-02"].severity == "critical"
    suggestion = findings["DSC-01"].suggestion
    assert suggestion and suggestion.text == "Enjoy free setup this month. T&C apply."


def test_disclaimers_present_pass(session: Session) -> None:
    text = "Enjoy free setup. T&C apply. Try PayWise Pay Later. Subject to eligibility."
    assert check(DisclaimerChecker(), text, context(session, "email")) == []


def test_hyphenated_free_is_not_an_offer_trigger(session: Session) -> None:
    assert check(DisclaimerChecker(), "Simple, hassle-free payments.", context(session)) == []


# --- Channel ---------------------------------------------------------------------------


def test_x_length_and_hashtags(session: Session) -> None:
    text = "PayWise " * 40 + "#one #two #three"
    findings = check(ChannelChecker(), text, context(session, "x"))
    assert {f.rule.id for f in findings} == {"CHN-02"}
    assert any("280" in f.explanation for f in findings)
    assert [f.text for f in findings if f.text.startswith("#")] == ["#three"]


def test_number_sign_is_not_a_hashtag(session: Session) -> None:
    assert check(ChannelChecker(), "India's #1 app", context(session, "x")) == []


def test_email_subject_length(session: Session) -> None:
    text = "Subject: " + "A very long subject line that keeps going well past the limit"
    findings = check(ChannelChecker(), text, context(session, "email"))
    assert [f.rule.id for f in findings] == ["CHN-03"]


# --- Readability -----------------------------------------------------------------------


def test_long_sentence_flagged_on_consumer_channel(session: Session) -> None:
    long_sentence = " ".join(["merchants"] * 35) + "."
    findings = check(ReadabilityChecker(), long_sentence, context(session, "linkedin"))
    assert any(f.rule.id == "RDB-01" and "35 words" in f.explanation for f in findings)


def test_readability_skipped_for_press_release(session: Session) -> None:
    long_sentence = " ".join(["merchants"] * 35) + "."
    assert check(ReadabilityChecker(), long_sentence, context(session, "press_release")) == []


def test_low_flesch_score_flagged(session: Session) -> None:
    dense = (
        "Comprehensive interoperability considerations necessitate institutional "
        "standardisation. " * 8
    )
    findings = check(ReadabilityChecker(), dense, context(session, "blog"))
    assert any("Flesch" in f.explanation for f in findings)


# --- Style (TON-03) --------------------------------------------------------------------


def test_extra_exclamation_mark_in_linkedin_sample(session: Session) -> None:
    findings = check(StyleChecker(), LINKEDIN_SAMPLE, context(session))
    assert len(findings) == 1
    f = findings[0]
    assert f.rule.id == "TON-03"
    assert f.text == "Download today and never worry again!"
    assert f.suggestion and f.suggestion.text == "Download today and never worry again."


def test_all_caps_shouting(session: Session) -> None:
    findings = check(StyleChecker(), "Get it NOW, it is AMAZING.", context(session))
    assert [f.text for f in findings] == ["AMAZING"]
