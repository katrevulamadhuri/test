import os
import subprocess
import snowflake.connector

from validators.database_validator import validate_database



conn = snowflake.connector.connect(
    account=os.environ["ACCOUNT"],
    user=os.environ["USER"],
    password=os.environ["PASSWORD"],
    database=os.environ["DATABASE"]
)

cur = conn.cursor()

# ----------------------------------------------------
# Changed files from latest merge
# ----------------------------------------------------

result = subprocess.run(
    [
        "git",
        "diff",
        "--name-only",
        "HEAD~1",
        "HEAD",
        "--",
        "sql/"
    ],
    capture_output=True,
    text=True
)

changed_files = {
    f.strip()
    for f in result.stdout.splitlines()
    if f.endswith(".sql")
}

# ----------------------------------------------------
# Latest failed scripts
# ----------------------------------------------------

cur.execute("""
SELECT SCRIPT_NAME
FROM (
    SELECT
        SCRIPT_NAME,
        STATUS,
        ROW_NUMBER() OVER
        (
            PARTITION BY SCRIPT_NAME
            ORDER BY DEPLOYED_AT DESC
        ) RN
    FROM DEPLOYMENT_HISTORY
)
WHERE RN=1
AND STATUS='FAILED'
""")

failed_files = {
    f"sql/{row[0]}"
    for row in cur.fetchall()
}

files = sorted(changed_files | failed_files)

print("Files to Deploy")

for f in files:
    print(f)

# ----------------------------------------------------
# Deployment
# ----------------------------------------------------

failed = []

for file in files:

    script = os.path.basename(file)

    with open(file) as fp:
        sql = fp.read()

    try:

        print(f"Validating {script}")

        validate_database(sql)

        validate_dependencies(sql, cur)

        print(f"Deploying {script}")

        cur.execute(sql)

        cur.execute("""
        INSERT INTO DEPLOYMENT_HISTORY
        (
            SCRIPT_NAME,
            DEPLOYED_AT,
            DEPLOYED_BY,
            STATUS,
            ERROR_MESSAGE
        )
        VALUES
        (
            %s,
            CURRENT_TIMESTAMP(),
            CURRENT_USER(),
            'SUCCESS',
            NULL
        )
        """, (script,))

        conn.commit()

        print(f"{script} SUCCESS")

    except Exception as e:

        conn.rollback()

        cur.execute("""
        INSERT INTO DEPLOYMENT_HISTORY
        (
            SCRIPT_NAME,
            DEPLOYED_AT,
            DEPLOYED_BY,
            STATUS,
            ERROR_MESSAGE
        )
        VALUES
        (
            %s,
            CURRENT_TIMESTAMP(),
            CURRENT_USER(),
            'FAILED',
            %s
        )
        """, (script, str(e)))

        conn.commit()

        failed.append(script)

        print(e)

if failed:

    raise Exception(
        "Deployment failed for : "
        + ",".join(failed)
    )

cur.close()
conn.close()
