CREATE OR REPLACE PROCEDURE sample.test_proc()
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    RETURN 'Hello from SQL Stored Procedure!';
END;
$$;