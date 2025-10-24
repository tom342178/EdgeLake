"""
Blockchain Query Module

Generic, configuration-driven blockchain data access for EdgeLake MCP server.
Uses direct Python APIs to access blockchain metadata.

License: Mozilla Public License 2.0
"""

import logging
from typing import List, Set, Dict, Any

logger = logging.getLogger(__name__)


class BlockchainQuery:
    """
    Generic blockchain query interface driven by configuration.

    Provides direct access to blockchain metadata without command parsing.
    """

    def __init__(self):
        """Initialize blockchain query interface"""
        # Import blockchain metadata module on init
        from edge_lake.blockchain import metadata
        self.metadata = metadata

        logger.info("Blockchain query interface initialized")

    def get_all_databases(self) -> List[str]:
        """
        Get list of all unique databases across all companies.

        Returns:
            Sorted list of database names
        """
        databases = set()

        # Access the table_to_cluster_ global dict
        # Structure: {company: {dbms: {table: ...}}}
        table_to_cluster = self.metadata.table_to_cluster_

        for company, dbms_dict in table_to_cluster.items():
            for dbms in dbms_dict.keys():
                databases.add(dbms)

        db_list = sorted(list(databases))
        logger.debug(f"Found {len(db_list)} databases: {db_list}")
        return db_list

    def get_tables_for_database(self, database: str) -> List[str]:
        """
        Get list of all tables in a specific database across all companies.

        Args:
            database: Database name to query

        Returns:
            Sorted list of table names
        """
        tables = set()

        # Access the table_to_cluster_ global dict
        table_to_cluster = self.metadata.table_to_cluster_

        for company, dbms_dict in table_to_cluster.items():
            if database in dbms_dict:
                for table_name in dbms_dict[database].keys():
                    tables.add(table_name)

        table_list = sorted(list(tables))
        logger.debug(f"Found {len(table_list)} tables in database '{database}': {table_list}")
        return table_list

    def get_companies(self) -> List[str]:
        """
        Get list of all companies in blockchain metadata.

        Returns:
            Sorted list of company names
        """
        table_to_cluster = self.metadata.table_to_cluster_
        companies = sorted(list(table_to_cluster.keys()))
        logger.debug(f"Found {len(companies)} companies: {companies}")
        return companies

    def get_databases_for_company(self, company: str) -> List[str]:
        """
        Get list of databases for a specific company.

        Args:
            company: Company name

        Returns:
            Sorted list of database names
        """
        table_to_cluster = self.metadata.table_to_cluster_

        if company not in table_to_cluster:
            return []

        databases = sorted(list(table_to_cluster[company].keys()))
        logger.debug(f"Found {len(databases)} databases for company '{company}': {databases}")
        return databases

    def execute_query(self, query_type: str, **kwargs) -> Any:
        """
        Generic query execution driven by configuration.

        Args:
            query_type: Type of query to execute
            **kwargs: Query-specific parameters

        Returns:
            Query result

        Raises:
            ValueError: If query_type is unknown
        """
        query_map = {
            'get_all_databases': self.get_all_databases,
            'get_tables_for_database': self.get_tables_for_database,
            'get_companies': self.get_companies,
            'get_databases_for_company': self.get_databases_for_company,
        }

        if query_type not in query_map:
            raise ValueError(f"Unknown blockchain query type: {query_type}")

        query_func = query_map[query_type]

        # Call with appropriate arguments
        return query_func(**kwargs)
