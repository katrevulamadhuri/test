import os
import sqlparse
from sql_metadata import Parser

EXPECTED_DATABASE = os.environ["DATABASE"].upper()


def validate_database(sql):

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
