import os
import re
import subprocess
import snowflake.connector

from validators.database_validator import validate_database



# ============================================================
# Extract objects being CREATED / ALTERED by the SQL file
# ============================================================

def get_objects_deployed(sql):

    pattern = re.compile(
        r"""
        \b
        (?:
            CREATE\s+(?:OR\s+REPLACE\s+)?
            |
            ALTER\s+
        )
        (?:
            TABLE
            |
            VIEW
            |
            STAGE
            |
            TASK
            |
            STREAM
            |
            PROCEDURE
            |
            FUNCTION
        )
        \s+
        (?:
            IF\s+NOT\s+EXISTS\s+
        )?
        (
            [A-Za-z0-9_$"-]+
            (?:
                \.[A-Za-z0-9_$"-]+
            ){0,2}
        )
        """,
        re.IGNORECASE | re.VERBOSE
    )

    matches = pattern.findall(sql)

    objects = []

    for obj in matches:

        obj = obj.strip()

        if obj not in objects:
            objects.append(obj)

    return ", ".join(objects)


# ============================================================
# Snowflake Connection
# ============================================================

conn = snowflake.connector.connect(
    account=os.environ["ACCOUNT"],
    user=os.environ["USER"],
    password=os.environ["PASSWORD"],
    database=os.environ["DATABASE"]
)

cur = conn.cursor()


try:

    # ========================================================
    # Get files changed in CURRENT merge
    # ========================================================

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
        text=True,
        check=True
    )

    changed_files = sorted(
        {
            file.strip()
            for file in result.stdout.splitlines()
            if file.strip().endswith(".sql")
        }
    )

    print("========================================")
    print("Files changed in current merge")
    print("========================================")

    if not changed_files:

        print("No SQL files changed.")

    for file in changed_files:

        print(file)


    # ========================================================
    # Deployment
    # ========================================================

    failed = []

    for file in changed_files:

        script_name = os.path.basename(file)

        print()
        print("========================================")
        print(f"Processing: {script_name}")
        print("========================================")

        # ----------------------------------------------------
        # Read SQL
        # ----------------------------------------------------

        with open(
            file,
            "r",
            encoding="utf-8"
        ) as fp:

            sql = fp.read()


        # ----------------------------------------------------
        # Identify objects
        # ----------------------------------------------------

        objects_deployed = get_objects_deployed(sql)

        print(
            f"Objects in script: "
            f"{objects_deployed or 'None detected'}"
        )


        try:

            # =================================================
            # Database Validation
            # =================================================

            print("Running database validation...")

            validate_database(sql)

            print("Database validation PASSED")

            # =================================================
            # Execute SQL
            # =================================================

            print(f"Deploying {script_name}...")

            cur.execute(sql)


            # =================================================
            # Record SUCCESS
            # =================================================

            cur.execute(
                """
                INSERT INTO DEPLOYMENT_HISTORY
                (
                    SCRIPT_NAME,
                    OBJECTS_DEPLOYED,
                    DEPLOYED_AT,
                    DEPLOYED_BY,
                    STATUS,
                    ERROR_MESSAGE
                )
                VALUES
                (
                    %s,
                    %s,
                    CURRENT_TIMESTAMP(),
                    CURRENT_USER(),
                    'SUCCESS',
                    NULL
                )
                """,
                (
                    script_name,
                    objects_deployed
                )
            )

            conn.commit()

            print(
                f"{script_name} deployed successfully."
            )


        except Exception as e:

            error_message = str(e)

            print()
            print(
                f"{script_name} FAILED"
            )

            print(
                f"Error: {error_message}"
            )


            # ------------------------------------------------
            # Rollback current deployment
            # ------------------------------------------------

            conn.rollback()


            # ------------------------------------------------
            # Record FAILURE
            # ------------------------------------------------

            cur.execute(
                """
                INSERT INTO DEPLOYMENT_HISTORY
                (
                    SCRIPT_NAME,
                    OBJECTS_DEPLOYED,
                    DEPLOYED_AT,
                    DEPLOYED_BY,
                    STATUS,
                    ERROR_MESSAGE
                )
                VALUES
                (
                    %s,
                    %s,
                    CURRENT_TIMESTAMP(),
                    CURRENT_USER(),
                    'FAILED',
                    %s
                )
                """,
                (
                    script_name,
                    objects_deployed,
                    error_message
                )
            )

            conn.commit()


            failed.append(script_name)

            # Continue deploying remaining changed files
            continue


    # ========================================================
    # Final result
    # ========================================================

    if failed:

        print()
        print("========================================")
        print("DEPLOYMENT FAILED")
        print("========================================")

        print(
            "Failed scripts:"
        )

        for script in failed:

            print(
                f"  - {script}"
            )

        raise Exception(
            "Deployment failed for: "
            + ", ".join(failed)
        )


    print()
    print("========================================")
    print("DEPLOYMENT SUCCESSFUL")
    print("========================================")


finally:

    cur.close()
    conn.close()
