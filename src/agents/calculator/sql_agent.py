"""Text-to-SQL Agent for Financial Database Querying (Task 3.11).

Generates safe, schema-aware SELECT queries against MySQL / SQLite databases,
enforces read-only syntax guards, and returns structured query records.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.agents.base_agent import BaseAgent, track_tokens
from src.database.mysql_client import MySQLClient
from src.utils.llm_client import get_default_llm
from src.utils.logger import get_logger

logger = get_logger("src.agents.calculator.sql_agent")

_SENTINEL = object()


class SQLQueryResult(BaseModel):
    """Encapsulates the result of executing an SQL query."""
    query_sql: str
    data: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    success: bool = True
    error: Optional[str] = None


class SQLSecurityError(Exception):
    """Raised when an unsafe or non-SELECT SQL statement is detected."""
    pass


class SQLAgent(BaseAgent):
    """Agent translating natural language financial questions into safe SQL SELECT queries."""

    # Prohibited SQL keywords
    FORBIDDEN_SQL_PATTERNS = [
        r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bINSERT\b",
        r"\bTRUNCATE\b", r"\bALTER\b", r"\bCREATE\b", r"\bGRANT\b",
        r"\bREVOKE\b", r"\bEXEC\b", r"\bEXECUTE\b", r"\bINTO\b",
    ]

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        llm: Any = _SENTINEL,
        prompt_template: str = "sql_agent",
        db_client: Optional[MySQLClient] = None,
    ):
        resolved_llm = get_default_llm("calculator") if llm is _SENTINEL else llm
        super().__init__(
            config=config,
            llm=resolved_llm,
            prompt_template=prompt_template,
        )
        self.db_client = db_client or MySQLClient()

    def validate_sql(self, sql_query: str) -> str:
        """
        Validates that the SQL query is strictly a SELECT statement.
        """
        cleaned_sql = sql_query.strip().rstrip(";")
        if not cleaned_sql.upper().startswith("SELECT"):
            raise SQLSecurityError("Chỉ cho phép câu lệnh bắt đầu bằng 'SELECT'.")

        for pattern in self.FORBIDDEN_SQL_PATTERNS:
            if re.search(pattern, cleaned_sql, re.IGNORECASE):
                raise SQLSecurityError(f"Phát hiện từ khóa SQL bị cấm theo mẫu: '{pattern}'")

        return cleaned_sql

    def extract_sql_from_text(self, text: str) -> str:
        """
        Extracts SQL code block from LLM output.
        """
        # Look for ```sql ... ``` block
        sql_match = re.search(r"```(?:sql)?\s*(SELECT[\s\S]*?)```", text, re.IGNORECASE)
        if sql_match:
            return sql_match.group(1).strip()

        # Fallback: look for direct SELECT query
        direct_match = re.search(r"(SELECT[\s\S]+)", text, re.IGNORECASE)
        if direct_match:
            return direct_match.group(1).strip()

        return text.strip()

    def format_prompt(self, query: str, ticker: str, years: Any, quarter: Any) -> str:
        """Renders the user prompt from the loaded YAML template."""
        user_tmpl = self.prompt_template.get("user_template", "")
        return user_tmpl.format(
            query=query,
            ticker=ticker,
            years=years,
            quarter=quarter,
        )

    @track_tokens
    def generate_sql(
        self,
        query: str,
        ticker: str = "FPT",
        years: Optional[List[int]] = None,
        quarter: Optional[int] = None,
    ) -> str:
        """
        Prompts the LLM to generate an optimized SQL SELECT query.
        """
        if self.llm is not None:
            try:
                formatted_prompt = self.format_prompt(
                    query=query,
                    ticker=ticker.strip().upper(),
                    years=years if years else "Tất cả các năm có sẵn",
                    quarter=quarter if quarter is not None else "0 (hoặc tất cả các quý)",
                )
                response = self.llm.invoke(formatted_prompt)
                raw_text = response.content if hasattr(response, "content") else str(response)
                sql = self.extract_sql_from_text(raw_text)
                return self.validate_sql(sql)
            except Exception as e:
                logger.warning(f"LLM SQL generation error ({e}). Falling back to deterministic SQL engine.")

        # Offline heuristic fallback if LLM is not provided or fails
        return self._generate_heuristic_sql(query, ticker, years, quarter)

    def _generate_heuristic_sql(
        self,
        query: str,
        ticker: str,
        years: Optional[List[int]],
        quarter: Optional[int],
    ) -> str:
        """Rule-based fallback SQL generator for offline execution."""
        q_lower = query.lower()
        where_clauses = [f"ticker = '{ticker.upper()}'"]

        if years:
            years_str = ", ".join(map(str, years))
            where_clauses.append(f"fiscal_year IN ({years_str})")

        if quarter is not None and quarter > 0:
            where_clauses.append(f"fiscal_quarter = {quarter}")

        item_conditions = []
        if "doanh thu" in q_lower or "doanh số" in q_lower or "revenue" in q_lower:
            item_conditions.append("line_item LIKE '%Doanh số%' OR line_item LIKE '%Doanh thu%'")
        if "lợi nhuận" in q_lower or "lãi" in q_lower or "profit" in q_lower or "margin" in q_lower:
            item_conditions.append("line_item LIKE '%Lợi nhuận%' OR line_item LIKE '%Lãi%'")
        if "roe" in q_lower or "roa" in q_lower or "dupont" in q_lower or "tài sản" in q_lower or "vốn" in q_lower or "tài chính" in q_lower:
            item_conditions.append("line_item LIKE '%TÀI SẢN%' OR line_item LIKE '%VỐN CHỦ SỞ HỮU%' OR line_item LIKE '%Lãi/(lỗ) thuần sau thuế%'")
        if "nợ" in q_lower or "debt" in q_lower:
            item_conditions.append("line_item LIKE '%NỢ%' OR line_item LIKE '%Phải trả%'")

        if item_conditions:
            combined_items = " OR ".join(f"({c})" for c in item_conditions)
            where_clauses.append(f"({combined_items})")

        where_stmt = " AND ".join(where_clauses)
        return f"SELECT fiscal_year, fiscal_quarter, report_type, line_item, value, unit FROM financial_data WHERE {where_stmt} ORDER BY fiscal_year, fiscal_quarter;"

    def execute_query(self, sql_query: str) -> SQLQueryResult:
        """
        Validates and executes a SQL SELECT query against MySQL / SQLite.
        """
        try:
            safe_sql = self.validate_sql(sql_query)
            logger.info(f"Executing SQL query: {safe_sql}")
            records = self.db_client.fetch_all(safe_sql)
            return SQLQueryResult(
                query_sql=safe_sql,
                data=records,
                row_count=len(records),
                success=True,
            )
        except SQLSecurityError as sec_err:
            logger.error(f"SQL Security check failed: {sec_err}")
            return SQLQueryResult(
                query_sql=sql_query,
                data=[],
                row_count=0,
                success=False,
                error=str(sec_err),
            )
        except Exception as db_err:
            logger.error(f"Database execution error: {db_err}")
            return SQLQueryResult(
                query_sql=sql_query,
                data=[],
                row_count=0,
                success=False,
                error=str(db_err),
            )

    def invoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main invocation method compliant with BaseAgent pipeline state.
        """
        query = state.get("query", "")
        ticker = state.get("company_ticker", "FPT")
        years = state.get("fiscal_years")
        quarter = state.get("fiscal_quarter")

        sql = self.generate_sql(query=query, ticker=ticker, years=years, quarter=quarter)
        res = self.execute_query(sql)

        # Fallback to heuristic SQL if generated query failed or returned empty results
        if not res.success or res.row_count == 0:
            logger.info("LLM SQL query returned 0 rows or failed. Applying deterministic financial query fallback...")
            fallback_sql = self._generate_heuristic_sql(query=query, ticker=ticker, years=years, quarter=quarter)
            res = self.execute_query(fallback_sql)

        state["sql_query"] = res.query_sql
        state["sql_data"] = res.data
        state["sql_success"] = res.success
        if not res.success:
            state.setdefault("errors", []).append(f"SQLAgent error: {res.error}")

        return state
