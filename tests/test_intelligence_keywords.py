from app.intelligence.batching import PostItem
from app.intelligence.keywords import (
    merge_tfidf_keywords,
    tfidf_crosscheck,
    tfidf_top_terms,
)
from app.schemas.intelligence import KeywordTag


def test_tfidf_top_terms_surfaces_distinctive_words():
    corpus = [
        "kubernetes autoscaling keeps clusters healthy under heavy load",
        "kubernetes autoscaling and cloud cost control for platform teams",
        "employer branding stories from our engineering culture week",
    ]
    terms = tfidf_top_terms(corpus, top_n=6)
    assert len(terms) == 3
    # TF-IDF favours each doc's distinctive vocabulary
    assert any("clusters" in t or "healthy" in t or "load" in t for t in terms[0])
    assert any("branding" in t or "culture" in t or "engineering" in t for t in terms[2])
    # a term shared by every doc should not dominate any single doc's top list
    assert all(t != "kubernetes" for t in terms[2])


def test_tfidf_top_terms_handles_tiny_corpus():
    assert tfidf_top_terms(["only one doc"], top_n=5) == [[]]
    assert tfidf_top_terms(["", "   "], top_n=5) == [[], []]


def test_merge_only_adds_missing_terms_tagged_tfidf():
    existing = [KeywordTag(term="cloud", category="industry_term")]
    merged = merge_tfidf_keywords(existing, ["cloud", "autoscaling", "clusters"])
    terms = {t.term: t for t in merged}
    assert terms["cloud"].source == "llm"  # untouched
    assert terms["autoscaling"].source == "tfidf"
    assert terms["autoscaling"].category == "frequent"
    assert terms["clusters"].source == "tfidf"


def test_tfidf_crosscheck_merges_across_run_corpus():
    items = [
        PostItem(1, 0, "kubernetes autoscaling for platform teams", "text"),
        PostItem(2, 1, "kubernetes security posture and platform hardening", "text"),
    ]
    llm_keywords = {0: [KeywordTag(term="platform", category="frequent")], 1: []}
    merged = tfidf_crosscheck(items, llm_keywords, top_n=4)
    assert set(merged) == {0, 1}
    assert any(t.source == "tfidf" for t in merged[0])
    assert any(t.source == "tfidf" for t in merged[1])
