import string

import prompts


def _all_prompt_names():
    return [n for n in dir(prompts) if n.endswith("_prompt")]


def test_at_least_21_prompts_defined():
    # Guards against the duplicate-definition bug this file used to have —
    # if this number drops, something got silently overwritten again.
    assert len(_all_prompt_names()) >= 21


def test_every_prompt_name_is_unique():
    names = _all_prompt_names()
    assert len(names) == len(set(names))


def test_every_prompt_starts_with_role():
    for name in _all_prompt_names():
        tmpl = getattr(prompts, name)
        assert tmpl.strip().startswith("ROLE"), f"{name} does not start with ROLE"


def test_every_prompt_has_output_contract_and_failure_path():
    for name in _all_prompt_names():
        tmpl = getattr(prompts, name)
        assert "OUTPUT CONTRACT" in tmpl, f"{name} missing OUTPUT CONTRACT"
        assert "FAILURE PATH" in tmpl, f"{name} missing FAILURE PATH"


def test_every_prompt_format_placeholders_parse_cleanly():
    formatter = string.Formatter()
    for name in _all_prompt_names():
        tmpl = getattr(prompts, name)
        fields = set(f for _, f, _, _ in formatter.parse(tmpl) if f)
        assert len(fields) >= 1, f"{name} has no fillable placeholder"


def test_business_question_prompt_formats_with_expected_fields():
    result = prompts.BusinessQuestionChain_prompt.format(question="why?", schema={})
    assert "why?" in result


def test_sql_generation_prompt_formats_with_expected_fields():
    result = prompts.render_dialect_sql_template("postgresql").format(
        question="why?", schema={}, business_context={}, latest_date="2024-01-01"
    )
    assert "2024-01-01" in result
