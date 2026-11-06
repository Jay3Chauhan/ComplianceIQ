"""Unit tests for the rule-based answer verifier."""

from llm.verifier import extract_claims, rule_check, verify_answer


def test_extract_claims_keeps_citations_and_skips_fragments() -> None:
    answer = (
        "Periodic updation is required at least once every two years for high risk customers [1].\n\n"
        "**Details:**\n"
        "- Medium risk customers must be updated once in every eight years. [1]\n"
        "- PAN must be verified with the issuing authority [2].\n"
        "**Not covered in the loaded documents:** penalty amounts."
    )
    claims = extract_claims(answer)
    assert len(claims) == 3
    assert claims[0].citations == [1]
    assert claims[1].citations == [1]
    assert claims[2].citations == [2]


def test_rule_check_flags_invalid_citations_and_numbers(sample_chunks) -> None:
    answer = "High risk customers must be updated every 3 years [1]. Low risk customers every ten years [5]."
    _, invalid, uncited, numbers = rule_check(answer, sample_chunks)
    assert invalid == [5]
    assert uncited == []
    assert numbers == ["3"]


def test_number_words_in_sources_count_as_supported(sample_chunks) -> None:
    answer = "High risk customers must be updated at least once in every 2 years [1]."
    _, _, _, numbers = rule_check(answer, sample_chunks)
    assert numbers == []


def test_verify_answer_verified(sample_chunks) -> None:
    answer = (
        "Periodic updation must happen at least once every two years for high risk customers [1]. "
        "REs shall carry out PAN verification with the issuing authority [2]."
    )
    report = verify_answer(answer, sample_chunks, use_llm=False)
    assert report.status == "verified"
    assert report.score == 1.0
    assert not report.needs_repair


def test_verify_answer_uncited_claims_reduce_score(sample_chunks) -> None:
    answer = (
        "Periodic updation must happen at least once every two years for high risk customers. "
        "Customers can also be onboarded through a branch visit without any documents at all."
    )
    report = verify_answer(answer, sample_chunks, use_llm=False)
    assert report.status == "unverified"
    assert report.needs_repair
    assert len(report.uncited_claims) == 2


def test_verify_answer_not_applicable_without_sources() -> None:
    assert verify_answer("Anything at all here for testing.", []).status == "not_applicable"


def test_citation_ranges_are_expanded(sample_chunks) -> None:
    answer = "Periodic updation and PAN verification requirements both apply to REs [1-2]."
    _, invalid, _, _ = rule_check(answer, sample_chunks)
    assert invalid == []
