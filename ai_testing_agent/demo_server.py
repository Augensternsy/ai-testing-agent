# -*- coding: utf-8 -*-
"""
Safe Demo Backend entry point.

Run with:
    uvicorn ai_testing_agent.demo_server:app --host 0.0.0.0 --port 8000

Or:
    python -m ai_testing_agent.demo_server
"""

from .demo_api import create_demo_app

app = create_demo_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "ai_testing_agent.demo_server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
