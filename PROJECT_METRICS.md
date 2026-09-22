# Verified Project Metrics

Only facts produced by real runs in this repository are recorded.
No accuracy / performance / coverage / efficiency percentages are claimed.

- Verification date: 2026-09-23
- Runtime: Python 3.13.5 (Windows local); CI targets Ubuntu + Python 3.13
- Real LLM: DeepSeek-compatible endpoint, model `deepseek-v3` (key provided via `.env`, never logged)

## Regression (deterministic + mocked; no API key required)

- Total: **89**
- Passed: **89**
- Failed: **0**
- Skipped: **0**
- Command: `pytest tests/ --basetemp=.pytest_tmp`

Per-file distribution:

| File | Stage | Tests |
|---|---|---|
| test_api_schema_parser.py | 1 | 7 |
| test_api_test_case_generator.py | 2 (LLM mocked; incl. 5 contract-guard tests) | 12 |
| test_test_code_generator.py | 3 | 10 |
| test_test_runner.py | 4 | 15 |
| test_failure_analyzer.py | 5 | 15 |
| test_safe_test_repair.py | 5 (anti-gaming safety) | 23 |
| test_agent_orchestrator.py | 5 | 7 |

## End-to-end demos (real runs)

- Stage 4 API E2E (`demo_run_tests.py`): **PASS** — FastAPI → PyTest → JUnit/JSON, 11/11
  (executes the generated `generated_tests/test_login.py`; count reflects the currently generated file)
- Stage 5 controlled-repair E2E (`demo_agent_pipeline.py`): **PASS**
  - With key: real-LLM repair of a `NameError` (analyzed `test_code_error`, confidence 0.92) → re-run 1/1 PASS, repair attempts = 1
  - Without key: deterministic mock fallback path also PASS (prints `REAL_LLM_E2E = NOT RUN` for the LLM dependency and still completes the repair loop)
- Real DeepSeek E2E (`demo_real_llm_pipeline.py`): **PASS**
  - RAG used: **true** (real local Chroma retrieval before the LLM call)
  - Generated cases: **12**
  - Schema-valid / executable cases: **12**
  - Contract-conflict cases rejected by the deterministic guard: **0** on this run
  - Structural-invalid cases: **0**
  - Generated code `compile()`: **success**
  - PyTest: **12 total / 12 passed / 0 failed / 0 errors / 0 skipped**
  - Covered `test_type`: normal, boundary, exception
  - Covered `expected_status`: 200, 401, 422
  - Artifact: `reports/real_llm_e2e_report.json`
- All-five-stage orchestrator (`run_ai_testing_pipeline.py`): mechanism **runs end-to-end**
  - 3 OpenAPI paths → 26 real-LLM cases → 3 generated files
  - Initial run: 22/26 passed; `/login` 11/11, `/health` 5/5
  - 4 `/users/{id}` failures were classified as **non-`test_code_error`** (LLM assumed
    positive/int32/required constraints not present in the schema) and the agent correctly
    **declined to auto-rewrite assertions**, emitting analysis reports instead

## Safety

- Failure categories: **5** — `test_code_error`, `api_defect`, `test_data_error`, `environment_error`, `unknown`
- Repair admission: `category == test_code_error` AND `confidence >= 0.80` AND `repair_allowed == true`
- Maximum repair attempts: **2** (default **1**)
- Every repair: backup first, append-only `audit.jsonl`, `compile()` check,
  no fewer `test_` functions, no fewer assertions, dangerous-call and skip/xfail rejection
- Only `generated_tests/` is writable by the repair agent

## Scope

- Demo endpoints: `POST /login`, `GET /users/{user_id}`, `GET /health`
- HTTP methods exercised by the demo: **GET, POST** (the OpenAPI parser is method-agnostic)
- Five-stage core Python modules: **10** (parser, case generator, RAG build, code generator,
  runner, failure analyzer, safe repair, orchestrator, shared config, pipeline runner)
- Direct runtime dependencies pinned in `requirements.txt`: **13**
- RAG knowledge source: `docs/软件测试规范.md` (testing standard), chunked 500 chars / 50 overlap
- RAG stack: langchain-chroma 1.1.0 + langchain-huggingface 1.2.2, embedding `BAAI/bge-base-zh-v1.5`

## CI

- `.github/workflows/tests.yml` configured for Ubuntu on push/PR; installs
  `requirements.txt` + editable package and runs the 7 test files with an empty
  `OPENAI_API_KEY` (LLM paths mocked). The real-LLM demo is intentionally excluded.
- Status note: CI workflow has been authored but **not yet executed on GitHub**
  (no remote repository has been created or pushed); no remote CI badge result is claimed.
