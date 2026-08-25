"""
MySQL Database Client with Connection Pool & Automatic Local SQLite Fallback.
Reads configuration from configs/database.yaml and manages database transactions safely.
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import yaml

from src.utils.logger import get_logger

logger = get_logger("src.database.mysql_client")


class MySQLClient:
    """
    Robust database client for financial analysis storage.
    Connects to MySQL 8.0 with connection pooling; automatically falls back to SQLite
    if MySQL service is unreachable, ensuring zero interruption during local development.
    """

    def __init__(self, config_path: Optional[str | Path] = None):
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.config_path = (
            Path(config_path) if config_path else self.project_root / "configs" / "database.yaml"
        )
        self.config = self._load_config()

        self.is_sqlite = False
        self.mysql_pool = None
        self._sqlite_path = self.project_root / "data" / "financial_app.db"
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_connection()

    def _load_config(self) -> Dict[str, Any]:
        """Loads MySQL connection parameters from YAML config."""
        if not self.config_path.exists():
            logger.warning(f"Database config not found at {self.config_path}. Using default settings.")
            return {}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
                return cfg.get("mysql", {})
        except Exception as e:
            logger.error(f"Error reading database.yaml: {e}")
            return {}

    def _init_connection(self):
        """Attempts to initialize MySQL connection pool; falls back to SQLite if offline."""
        host = os.getenv(self.config.get("host_env", "MYSQL_HOST"), self.config.get("default_host", "localhost"))
        port = int(os.getenv(self.config.get("port_env", "MYSQL_PORT"), self.config.get("default_port", 3306)))
        database = os.getenv(self.config.get("database_env", "MYSQL_DATABASE"), "financial_db")
        user = os.getenv(self.config.get("user_env", "MYSQL_USER"), "root")
        password = os.getenv(self.config.get("password_env", "MYSQL_PASSWORD"), "")

        pool_cfg = self.config.get("pool", {})
        pool_size = pool_cfg.get("pool_size", 5)
        pool_name = pool_cfg.get("pool_name", "mysql_app_pool")

        try:
            # Try PyMySQL or mysql.connector
            try:
                import pymysql
                from dbutils.pooled_db import PooledDB

                self.mysql_pool = PooledDB(
                    creator=pymysql,
                    maxconnections=pool_size,
                    host=host,
                    port=port,
                    user=user,
                    password=password,
                    database=database,
                    charset=self.config.get("charset", "utf8mb4"),
                    cursorclass=pymysql.cursors.DictCursor,
                    autocommit=False,
                )
                # Test connection
                conn = self.mysql_pool.connection()
                conn.ping()
                conn.close()
                self.is_sqlite = False
                logger.info(f"Connected to MySQL on {host}:{port}/{database} (Pool: {pool_name}).")
                return
            except Exception:
                pass

            # Alternative: try mysql.connector
            import mysql.connector
            from mysql.connector import pooling

            self.mysql_pool = pooling.MySQLConnectionPool(
                pool_name=pool_name,
                pool_size=pool_size,
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                charset=self.config.get("charset", "utf8mb4"),
                autocommit=False,
            )
            test_conn = self.mysql_pool.get_connection()
            test_conn.ping(reconnect=True)
            test_conn.close()
            self.is_sqlite = False
            logger.info(f"Connected to MySQL via connector on {host}:{port}/{database}.")
            return

        except Exception as err:
            logger.warning(
                f"MySQL server is offline ({err}). Switching to Local SQLite fallback: {self._sqlite_path.name}"
            )
            self.is_sqlite = True

    @contextmanager
    def get_connection(self) -> Generator[Any, None, None]:
        """Provides a database connection from pool or SQLite."""
        if self.is_sqlite:
            conn = sqlite3.connect(str(self._sqlite_path))
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()
        else:
            if hasattr(self.mysql_pool, "connection"):
                conn = self.mysql_pool.connection()
            else:
                conn = self.mysql_pool.get_connection()
            try:
                yield conn
            finally:
                conn.close()

    def execute(self, query: str, params: Optional[Union[Tuple, List, Dict]] = None) -> int:
        """Executes a single SQL query and commits transaction."""
        query_sql = self._adapt_query(query)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query_sql, params or ())
                conn.commit()
                rowcount = cursor.rowcount
                return rowcount
            except Exception as e:
                conn.rollback()
                logger.error(f"SQL execute error: {e}\nQuery: {query_sql}")
                raise
            finally:
                cursor.close()

    def execute_many(self, query: str, params_list: List[Union[Tuple, List, Dict]]) -> int:
        """Executes batch SQL queries within a single transaction."""
        if not params_list:
            return 0
        query_sql = self._adapt_query(query)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(query_sql, params_list)
                conn.commit()
                rowcount = cursor.rowcount
                return rowcount
            except Exception as e:
                conn.rollback()
                logger.error(f"SQL execute_many error: {e}\nQuery: {query_sql}")
                raise
            finally:
                cursor.close()

    def fetch_one(
        self, query: str, params: Optional[Union[Tuple, List, Dict]] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetches a single row as a dictionary."""
        query_sql = self._adapt_query(query)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query_sql, params or ())
                row = cursor.fetchone()
                if row is None:
                    return None
                return dict(row)
            finally:
                cursor.close()

    def fetch_all(
        self, query: str, params: Optional[Union[Tuple, List, Dict]] = None
    ) -> List[Dict[str, Any]]:
        """Fetches all matching rows as a list of dictionaries."""
        query_sql = self._adapt_query(query)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(query_sql, params or ())
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
            finally:
                cursor.close()

    def ping(self) -> bool:
        """Checks if the database connection is alive."""
        try:
            res = self.fetch_one("SELECT 1 AS alive")
            return res is not None and (res.get("alive") == 1 or res.get("1") == 1)
        except Exception:
            return False

    def _adapt_query(self, query: str) -> str:
        """Translates MySQL query placeholders and upsert syntax for SQLite if in fallback mode."""
        if not self.is_sqlite:
            return query

        adapted = query.strip()
        # Convert %s placeholder to ? for SQLite
        adapted = adapted.replace("%s", "?")

        # Adapt MySQL 'INSERT ... ON DUPLICATE KEY UPDATE' to SQLite 'INSERT ... ON CONFLICT DO UPDATE'
        if "ON DUPLICATE KEY UPDATE" in adapted:
            parts = adapted.split("ON DUPLICATE KEY UPDATE")
            base_insert = parts[0].strip()
            update_clause = parts[1].strip()

            # Identify target conflict columns based on table
            if "financial_data" in base_insert:
                conflict_target = "(ticker, fiscal_year, fiscal_quarter, report_type, line_code, line_item)"
                # Replace VALUES(col) with excluded.col for SQLite
                import re
                update_clean = re.sub(r"VALUES\((\w+)\)", r"excluded.\1", update_clause, flags=re.IGNORECASE)
                adapted = f"{base_insert} ON CONFLICT{conflict_target} DO UPDATE SET {update_clean}"
            elif "companies" in base_insert:
                conflict_target = "(ticker)"
                import re
                update_clean = re.sub(r"VALUES\((\w+)\)", r"excluded.\1", update_clause, flags=re.IGNORECASE)
                adapted = f"{base_insert} ON CONFLICT{conflict_target} DO UPDATE SET {update_clean}"

        return adapted
