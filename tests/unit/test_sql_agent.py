"""Unit tests for src.agents.calculator.sql_agent."""

import pytest
from src.agents.calculator.sql_agent import SQLAgent, SQLSecurityError


def test_validate_sql_accepts_select():
    agent = SQLAgent()
    valid_query = "SELECT * FROM financial_data WHERE ticker = 'FPT';"
    cleaned = agent.validate_sql(valid_query)
    assert cleaned == "SELECT * FROM financial_data WHERE ticker = 'FPT'"


def test_validate_sql_rejects_non_select():
    agent = SQLAgent()
    bad_queries = [
        "DELETE FROM financial_data WHERE ticker = 'FPT'",
        "DROP TABLE companies",
        "INSERT INTO companies (ticker) VALUES ('TEST')",
        "UPDATE financial_data SET value = 0",
        "SELECT * FROM financial_data; DROP TABLE companies",
    ]
    for q in bad_queries:
        with pytest.raises(SQLSecurityError):
            agent.validate_sql(q)


def test_generate_heuristic_sql():
    agent = SQLAgent()
    sql = agent._generate_heuristic_sql(
        query="Lấy doanh thu của FPT năm 2023",
        ticker="FPT",
        years=[2023],
        quarter=None,
    )
    assert "ticker = 'FPT'" in sql
    assert "fiscal_year IN (2023)" in sql
    assert "line_item LIKE '%Doanh số%'" in sql
    assert sql.startswith("SELECT")


def test_execute_query_runs_against_db():
    agent = SQLAgent()
    # Query FPT 2023
    sql = "SELECT line_item, value FROM financial_data WHERE ticker = 'FPT' AND fiscal_year = 2023 LIMIT 5"
    res = agent.execute_query(sql)
    assert res.success is True
    assert res.row_count > 0
    assert len(res.data) > 0
    assert "line_item" in res.data[0]
