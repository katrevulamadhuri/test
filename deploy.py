
import os
import re
import subprocess
import snowflake.connector
import glob

# Custom validation function used to validate the database
from validators.database_validator import validate_database

# ---------------------------------------------------------
# Function: get_deployment_details
# Purpose:
#   Extract the Snowflake object name, object type, and
#   operation from the SQL script.
#
# Example:
#   CREATE TABLE DB.SCHEMA.CUSTOMER (...)
#
#   Output:
#   {
#       "object_name": "DB.SCHEMA.CUSTOMER",
#       "object_type": "TABLE",
#       "operation": "CREATE"
#   }
# ---------------------------------------------------------
def get_deployment_details(sql: str):
    
    # Regular expressions used to identify different sql operations
    patterns = [
        
        (r'CREATE\s+(?:OR\s+REPLACE\s+)?(TABLE|VIEW|STAGE|TASK|STREAM|FUNCTION|PROCEDURE)\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_.$"]+)', "CREATE"),
        (r'ALTER\s+(TABLE|VIEW|STAGE|TASK|STREAM)\s+([A-Za-z0-9_.$"]+)', "ALTER"),
        (r'INSERT\s+INTO\s+([A-Za-z0-9_.$"]+)', "INSERT"),
        (r'UPDATE\s+([A-Za-z0-9_.$"]+)', "UPDATE"),
        (r'DELETE\s+FROM\s+([A-Za-z0-9_.$"]+)', "DELETE"),
        (r'MERGE\s+INTO\s+([A-Za-z0-9_.$"]+)', "MERGE"),
        (r'TRUNCATE\s+TABLE\s+([A-Za-z0-9_.$"]+)', "TRUNCATE"),
    ]

    details = []

    for pattern, op in patterns:
        matches = re.findall(pattern, sql, flags=re.IGNORECASE)
        for m in matches:
            #CREATE and ALTER regex patterns return:
            #   m[0] = object type
            #   m[1] = object name
            if op in ("CREATE", "ALTER"):
                details.append({
                    "object_name": m[1],
                    "object_type": m[0].upper(),
                    "operation": op
                })
            # INSERT, UPDATE, DELETE, MERGE and TRUNCATE patterns return only the object name.
            else:
                details.append({
                    "object_name": m,
                    "object_type": "TABLE",
                    "operation": op
                })
    return details

# ---------------------------------------------------------
# Snowflake connection
# Connection details are obtained from environment variables.
# This is useful in GitHub Actions because credentials can be stored as GitHub Secrets instead of being hard-coded.
# ---------------------------------------------------------
conn = snowflake.connector.connect(
    account=os.environ["ACCOUNT"],
    user=os.environ["USER"],
    password=os.environ["PASSWORD"],
    database=os.environ["DATABASE"]
)

#URL of the current GitHub Actions workflow run.This value can be stored in DEPLOYMENT_HISTORY so that the deployment can be traced back to the CI/CD run.
run_url = os.environ.get("RUN_URL")
cur = conn.cursor()
before_sha = os.environ["GITHUB_BEFORE"]
after_sha = os.environ.get("GITHUB_SHA", "HEAD")

try:
    if before_sha == "0" * 40:
        before_sha = subprocess.run(
            ["git", "hash-object", "-t", "tree", "/dev/null"],
            capture_output=True, text=True
        ).stdout.strip()

    result = subprocess.run(
        [
            "git", "diff", "--name-only", before_sha, after_sha,
            "--",
            ".",
            ":!.github",
            ":!validators",
            ":!requirements.txt",
            ":!deploy.py",
            ":!README.md",
        ],
        capture_output=True,
        text=True,
        check=True
    )

    changed_files = [
        f.strip()
        for f in result.stdout.splitlines()
        if f.strip().endswith(".sql")
    ]

    order_files = [
        f.strip()
        for f in result.stdout.splitlines()
        if f.strip().endswith("deploy_order.txt")
    ]
# try:
#     # -----------------------------------------------------
#     # Identify files changed in the latest Git commit.
#     #
#     # HEAD~1 = previous commit
#     # HEAD   = current commit
#     # -- sql/
#     # means only changes under the sql directory are returned.
#     # -----------------------------------------------------
#     # result = subprocess.run(
#     #     ["git", "diff", "--name-only", "HEAD~1", "HEAD", "--", "sql/"],
#     #     capture_output=True,
#     #     text=True,
#     #     check=True
#     # )
#     if before_sha == "0" * 40:
#         before_sha = subprocess.run(
#             ["git", "hash-object", "-t", "tree", "/dev/null"],
#             capture_output=True, text=True
#         ).stdout.strip()
    
#   result = subprocess.run(
#     [
#         "git", "diff", "--name-only", before_sha, after_sha,
#         "--",
#         ".",
#         ":!.github",
#         ":!validators",
#         ":!requirements.txt",
#         ":!deploy.py",
#         ":!README.md",
#     ],
#     capture_output=True,
#     text=True,
#     check=True
# )
# #     result = subprocess.run(
# #     [
# #         "git", "diff", "--name-only", "HEAD^1", "HEAD",
# #         "--",
# #         ".",
# #         ":!.github",
# #         ":!validators",
# #         ":!requirements.txt",
# #         ":!deploy.py",
# #         ":!README.md",
# #     ],
# #     capture_output=True,
# #     text=True,
# #     check=True
# # )

#         # Get changed SQL files
#     changed_files = [
#         f.strip()
#         for f in result.stdout.splitlines()
#         if f.strip().endswith(".sql")
#     ]
#     # -----------------------------------------------------
#     # Check whether deploy_order.txt was also changed.
#     #
#     # This file can be used to control the order in which SQL files are deployed.
#     # Example:
#     #
#     # deploy_order.txt
#     # ----------------
#     # tables/customer.sql
#     # tables/orders.sql
#     # views/customer_view.sql
#     # -----------------------------------------------------
#     order_files = [
#         f.strip()
#         for f in result.stdout.splitlines()
#         if f.strip().endswith("deploy_order.txt")
#     ]  
    # -----------------------------------------------------
    # If deploy_order.txt exists, use it to determine the
    # deployment sequence.
    # -----------------------------------------------------
    if order_files:
        
        # Only one deployment-order file should be changed in a single deployment.
        if len(order_files) > 1:
            raise Exception(
                f"Multiple deployment order files found in this deployment: {order_files}"
            )
        order_file = order_files[0] 

        with open(order_file, "r", encoding="utf-8") as f:
            deploy_order = [
                line.strip()
                for line in f
                if line.strip() and not line.startswith("#")
            ]
            
        # List that will contain files in the required deployment order.
        ordered_files = []

        # Add changed files in the order specified in deploy_order.txt
        # for filename in deploy_order:
        #     path = filename if filename.startswith("sql/") else f"sql/{filename}"
        # Add changed files in the order specified in deploy_order.txt
        # deploy_order.txt entries must now be full relative paths from repo root,
        # e.g. "finance/create_view.sql", "sql/tables/customer.sql"
        for filename in deploy_order:
            if filename in changed_files:
                ordered_files.append(filename)
            # if path in changed_files:
            #     ordered_files.append(path)

        # Append any changed files not present in deploy_order.txt
        remaining = sorted(
            f for f in changed_files
            if f not in ordered_files
        )

        changed_files = ordered_files + remaining

    else:
        # Default alphabetical deployment
        changed_files = sorted(changed_files)
    
    # List used to keep track of scripts that failed.
    failed = []

    for file in changed_files:
        # Extract only the filename from the path.
        #
        # Example:
        # sql/tables/customer.sql
        #
        # becomes:
        # customer.sql
        
        script_name = os.path.basename(file)

        with open(file, encoding="utf-8") as fp:
            sql = fp.read()

        # -------------------------------------------------
        # Extract object information from the SQL.
        # This is later stored in DEPLOYMENT_HISTORY.
        # -------------------------------------------------
        deployment_details = get_deployment_details(sql)

        try:
            validate_database(sql)
            # validate_dependencies(sql, cur)

            cur.execute(sql)
          
            # If execution succeeds, insert one record into DEPLOYMENT_HISTORY for each object detected in the SQL file.

            for d in deployment_details:
                cur.execute("""
                    INSERT INTO DEPLOYMENT_HISTORY
                    (
                        SCRIPT_NAME,
                        OBJECT_NAME,
                        OBJECT_TYPE,
                        OPERATION,
                        DEPLOYED_AT,
                        DEPLOYED_BY,
                        STATUS,
                        LOG_URL
                    )
                    VALUES
                    (
                        %s,%s,%s,%s,
                        CURRENT_TIMESTAMP(),
                        CURRENT_USER(),
                        'SUCCESS',
                        %s
                       
                    )
                """, (
                    script_name,
                    d["object_name"],
                    d["object_type"],
                    d["operation"],
                    run_url
                ))

            conn.commit()

        except Exception as e:
            conn.rollback()
            print("=" * 60)
            print(f"FAILED : {script_name}")
            print(f"ERROR  : {e}")
            print("=" * 60)
            for d in deployment_details:
            # -------------------------------------------------
            # Record the failed deployment in DEPLOYMENT_HISTORY.
            # -------------------------------------------------
                cur.execute("""
                    INSERT INTO DEPLOYMENT_HISTORY
                    (
                        SCRIPT_NAME,
                        OBJECT_NAME,
                        OBJECT_TYPE,
                        OPERATION,
                        DEPLOYED_AT,
                        DEPLOYED_BY,
                        STATUS,
                        LOG_URL
                    )
                    VALUES
                    (
                        %s,%s,%s,%s,
                        CURRENT_TIMESTAMP(),
                        CURRENT_USER(),
                        'FAILED',
                        %s
                    )
                """, (
                    script_name,
                    d["object_name"],
                    d["object_type"],
                    d["operation"],
                    run_url
                ))

            conn.commit()
            failed.append(script_name)

    if failed:
        raise Exception("Deployment failed for: " + ", ".join(failed))

finally:
    cur.close()
    conn.close()
