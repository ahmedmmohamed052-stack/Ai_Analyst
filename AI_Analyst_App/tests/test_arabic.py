"""Arabic support: language flows to the LLM prompts, is stored with the report, and the PDF renders."""
import json


def _capture_prompts(monkeypatch):
    import chains
    prompts = []
    real = chains.client.chat_completion

    def spy(messages, **kw):
        prompts.append(messages[0]["content"])
        return real(messages, **kw)

    monkeypatch.setattr(chains.client, "chat_completion", spy)
    return prompts


def test_arabic_directive_added_to_interpretations_but_not_json_or_sql(client, subscribed_user, monkeypatch):
    prompts = _capture_prompts(monkeypatch)
    r = client.post("/analyze", json={"question": "Why?", "dataset_id": "ds1", "language": "ar"}, headers=subscribed_user)
    assert r.status_code == 200
    with_directive = [p for p in prompts if "OUTPUT LANGUAGE (mandatory)" in p]
    without = [p for p in prompts if "OUTPUT LANGUAGE (mandatory)" not in p]
    assert len(with_directive) >= 8
    # exactly the two strict-format stages stay untouched
    assert len(without) == 2
    assert any("NOW GENERATE THE SQL" in p for p in without)
    assert any('"target_metric"' in p and "NOW ANALYZE THIS" in p for p in without)
    assert r.json()["language"] == "ar"


def test_english_is_the_default_and_adds_no_directive(client, subscribed_user, monkeypatch):
    prompts = _capture_prompts(monkeypatch)
    r = client.post("/analyze", json={"question": "Why?", "dataset_id": "ds1"}, headers=subscribed_user)
    assert r.status_code == 200
    assert not any("OUTPUT LANGUAGE" in p for p in prompts)
    assert r.json()["language"] == "en"


def test_unknown_language_falls_back_to_english(client, subscribed_user, monkeypatch):
    prompts = _capture_prompts(monkeypatch)
    r = client.post("/analyze", json={"question": "Why?", "dataset_id": "ds1", "language": "xx"}, headers=subscribed_user)
    assert r.status_code == 200
    assert r.json()["language"] == "en"
    assert not any("OUTPUT LANGUAGE" in p for p in prompts)


def test_language_does_not_leak_between_requests(client, subscribed_user, monkeypatch):
    client.post("/analyze", json={"question": "a", "dataset_id": "ds1", "language": "ar"}, headers=subscribed_user)
    prompts = _capture_prompts(monkeypatch)
    client.post("/analyze", json={"question": "b", "dataset_id": "ds1", "language": "en"}, headers=subscribed_user)
    assert not any("OUTPUT LANGUAGE" in p for p in prompts)


def test_arabic_section_labels_in_more_analysis(monkeypatch):
    import chains
    monkeypatch.setattr(chains, "run_chain", lambda *a, **k: "نص")
    token = chains.set_output_language("ar")
    try:
        out = chains.moreanalysis_chain({"growth": {"x": 1}, "segmentation": {"region": {"y": 1}}})
    finally:
        chains.reset_output_language(token)
    assert "النمو: نص" in out and "التقسيم حسب region: نص" in out


def test_arabic_report_downloads_as_pdf(client, subscribed_user):
    r = client.post("/analyze", json={"question": "لماذا انخفضت الإيرادات؟", "dataset_id": "ds1", "language": "ar"}, headers=subscribed_user)
    report_id = r.json()["report_id"]
    r = client.get(f"/report/{report_id}/pdf", headers=subscribed_user)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


def test_arabic_pdf_generator_handles_mixed_text_and_page_count(tmp_path):
    from pdf_generator import generate_pipeline_pdf
    out = tmp_path / "ar.pdf"
    data = {
        "language": "ar",
        "question": "لماذا انخفضت الإيرادات في الربع الثالث (Q3)؟",
        "sql_query": "SELECT region, SUM(revenue) FROM sales GROUP BY region;",
        "insights": "انخفضت الإيرادات بنسبة 12% في منطقة North. " * 60,
        "business_context": {"target_metric": "revenue"},
        "quality_report": {"rows": 100, "nulls": {"a": 0}},
    }
    generate_pipeline_pdf(data, filename=str(out))
    assert out.read_bytes().startswith(b"%PDF")


def test_english_pdf_unchanged_path(tmp_path):
    from pdf_generator import generate_pipeline_pdf
    out = tmp_path / "en.pdf"
    generate_pipeline_pdf({"question": "Why?", "sql_query": "SELECT 1", "insights": "Fine."}, filename=str(out))
    assert out.read_bytes().startswith(b"%PDF")