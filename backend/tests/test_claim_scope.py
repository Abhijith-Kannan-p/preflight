"""Scope, hedged wording and first-person claims in the Claim Ledger."""

from app.engine.claims.detect import _as_brand
from app.engine.claims.scope import is_vague, out_of_scope


def test_facts_about_another_payment_method_or_store_are_out_of_scope() -> None:
    card_cashback = "PayWise Card offers 1% cashback on online purchases."
    assert out_of_scope("PayWise offers 10% cashback on every UPI payment.", card_cashback)
    assert out_of_scope(
        "PayWise is rated 4.8 out of 5 on the Apple App Store.",
        "The PayWise app is rated 4.6 out of 5 on the Google Play Store.",
    )
    # Same scope, or a fact that names everything: comparable.
    assert out_of_scope("PayWise Card gives 2% cashback online.", card_cashback) is None
    assert (
        out_of_scope(
            "PayWise accepts UPI.", "PayWise supports UPI, cards, net banking and wallets."
        )
        is None
    )


def test_hedged_wording_without_a_number_is_vague() -> None:
    assert is_vague("PayWise is trusted by millions of users.")
    assert is_vague("PayWise charges merchants less than most competitors.")
    assert not is_vague("PayWise serves over 12 million registered users.")
    assert not is_vague("PayWise Card has no annual fee.")


def test_first_person_claims_are_about_the_brand() -> None:
    assert _as_brand("We settle payments in 3 seconds") == "PayWise settle payments in 3 seconds"
    assert _as_brand("Our app is rated 4.9") == "PayWise's app is rated 4.9"
    assert _as_brand("Weekly reports are ready") == "Weekly reports are ready"
