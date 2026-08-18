import os
import sqlparse
from sql_metadata import Parser

# Get the expected database name from the environment variable DATABASE.

EXPECTED_DATABASE = os.environ["DATABASE"].upper()


def validate_database(sql):
    # -----------------------------------------------------
    # Parse the SQL statement using sql_metadata.
    # Parser analyzes the SQL and helps identify table and object references.
    # -----------------------------------------------------
    parser = Parser(sql)

    objects = parser.tables

    for obj in objects:

        parts = obj.split(".")

        if len(parts) == 3:

            db = parts[0].upper()

            if db != EXPECTED_DATABASE:

                raise Exception(
                    f"""
Database Validation Failed

Expected Database : {EXPECTED_DATABASE}

Found Database    : {db}

Object            : {obj}
"""
                )
