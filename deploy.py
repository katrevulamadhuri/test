
import os
import re
import subprocess
import snowflake.connector
import glob

from validators.database_validator import validate_database

def get_deployment_details(sql: str):
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
            if op in ("CREATE", "ALTER"):
                details.append({
                    "object_name": m[1],
                    "object_type": m[0].upper(),
                    "operation": op
                })
            else:
                details.append({
                    "object_name": m,
                    "object_type": "TABLE",
                    "operation": op
                })
    return details


conn = snowflake.connector.connect(
    account=os.environ["ACCOUNT"],
    user=os.environ["USER"],
    password=os.environ["PASSWORD"],
    database=os.environ["DATABASE"]
)
run_url = os.environ.get("RUN_URL")
cur = conn.cursor()

try:
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD", "--", "sql/"],
        capture_output=True,
        text=True,
        check=True
    )

        # Get changed SQL files
    changed_files = [
        f.strip()
        for f in result.stdout.splitlines()
        if f.strip().endswith(".sql")
    ]

    order_files = glob.glob("*deploy_order.txt")


    if order_files:
        order_file = order_files[0] 

        with open(order_file, "r", encoding="utf-8") as f:
            deploy_order = [
                line.strip()
                for line in f
                if line.strip() and not line.startswith("#")
            ]

        ordered_files = []

        # Add changed files in the order specified in deploy_order.txt
        for filename in deploy_order:
            path = filename if filename.startswith("sql/") else f"sql/{filename}"
            if path in changed_files:
                ordered_files.append(path)

        # Append any changed files not present in deploy_order.txt
        remaining = sorted(
            f for f in changed_files
            if f not in ordered_files
        )

        changed_files = ordered_files + remaining

    else:
        # Default alphabetical deployment
        changed_files = sorted(changed_files)

    failed = []

    for file in changed_files:
        script_name = os.path.basename(file)

        with open(file, encoding="utf-8") as fp:
            sql = fp.read()

        deployment_details = get_deployment_details(sql)

        try:
            validate_database(sql)
            # validate_dependencies(sql, cur)

            cur.execute(sql)

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
