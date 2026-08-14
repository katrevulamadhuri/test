CREATE OR REPLACE PROCEDURE public.get_view_order()
RETURNS TABLE ()
LANGUAGE SQL
AS
$$
BEGIN
    RETURN TABLE (
        SELECT *
        FROM public.view_order
    );
END;
$$;