# -*- coding: utf-8 -*-
"""
AI Agent Automated Testing Platform

Five-stage pipeline:
  Stage 1  FastAPI/OpenAPI -> Structured API Schema
  Stage 2  API Schema -> RAG -> DeepSeek -> Structured Test Cases
  Stage 3  Test Cases JSON -> Deterministic Template -> PyTest Code
  Stage 4  PyTest -> Execution -> JUnit XML / JSON Report
  Stage 5  Failure -> Analyzer -> Safe Repair -> Re-run
"""

__version__ = "1.0.0"
