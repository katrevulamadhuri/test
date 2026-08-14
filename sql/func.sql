CREATE OR REPLACE FUNCTION public.get_order_count()
RETURNS NUMBER
LANGUAGE SQL
AS
$$
    SELECT COUNT(*)
    FROM public.view_order
$$;