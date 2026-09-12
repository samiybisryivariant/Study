CREATE OR REPLACE VIEW public.support_ticket_risk_features AS
WITH ref_points AS (
    SELECT t.user_id, t.created_at AS ref_date, TRUE AS has_ticket
    FROM public.support_tickets t
    UNION ALL
    SELECT ls.user_id, ls.ref_date, FALSE AS has_ticket
    FROM (
        SELECT user_id, max(started_at) AS ref_date
        FROM public.sessions
        GROUP BY user_id
    ) ls
    WHERE ls.user_id NOT IN (SELECT user_id FROM public.support_tickets)
),
win AS (
    SELECT user_id, ref_date, has_ticket,
           ref_date - interval '30 days' AS win_start
    FROM ref_points
),
sess_agg AS (
    SELECT w.user_id,
           count(s.session_id) AS session_count_30d,
           avg(EXTRACT(EPOCH FROM (s.ended_at - s.started_at)) / 60.0) AS avg_session_duration_min_30d,
           count(DISTINCT date_trunc('day', s.started_at)) AS distinct_active_days_30d
    FROM win w
    LEFT JOIN public.sessions s
        ON s.user_id = w.user_id
       AND s.started_at >= w.win_start
       AND s.started_at < w.ref_date
    GROUP BY w.user_id
),
event_agg AS (
    SELECT w.user_id,
           count(e.event_id) AS total_events_30d,
           count(*) FILTER (WHERE e.event_type_id = 5)  AS search_events_30d,
           count(*) FILTER (WHERE e.event_type_id = 6)  AS product_view_events_30d,
           count(*) FILTER (WHERE e.event_type_id = 7)  AS add_to_cart_events_30d,
           count(*) FILTER (WHERE e.event_type_id = 8)  AS remove_from_cart_events_30d,
           count(*) FILTER (WHERE e.event_type_id = 10) AS checkout_started_30d,
           count(*) FILTER (WHERE e.event_type_id = 11) AS payment_failed_30d,
           count(*) FILTER (WHERE e.event_type_id = 12) AS purchase_events_30d
    FROM win w
    LEFT JOIN public.events e
        ON e.user_id = w.user_id
       AND e.event_timestamp >= w.win_start
       AND e.event_timestamp < w.ref_date
    GROUP BY w.user_id
),
order_agg AS (
    SELECT w.user_id,
           count(o.order_id) AS orders_total_30d,
           count(*) FILTER (WHERE o.order_status_id IN (2, 3)) AS orders_cancelled_refunded_30d
    FROM win w
    LEFT JOIN public.orders o
        ON o.user_id = w.user_id
       AND o.order_timestamp >= w.win_start
       AND o.order_timestamp < w.ref_date
    GROUP BY w.user_id
),
notif_agg AS (
    SELECT w.user_id,
           count(n.notification_id) AS notifications_sent_30d,
           count(n.opened_at) AS notifications_opened_30d
    FROM win w
    LEFT JOIN public.notifications n
        ON n.user_id = w.user_id
       AND n.sent_at >= w.win_start
       AND n.sent_at < w.ref_date
    GROUP BY w.user_id
),
review_agg AS (
    SELECT w.user_id,
           avg(r.rating) AS avg_review_rating_30d,
           count(r.review_id) AS review_count_30d
    FROM win w
    LEFT JOIN public.product_reviews r
        ON r.user_id = w.user_id
       AND r.created_at >= w.win_start
       AND r.created_at < w.ref_date
    GROUP BY w.user_id
)
SELECT
    w.user_id,
    w.ref_date,
    w.has_ticket,
    u.registration_date,
    u.country_id,
    u.gender,
    u.acquisition_source_id,
    s.session_count_30d,
    s.avg_session_duration_min_30d,
    s.distinct_active_days_30d,
    e.total_events_30d,
    e.search_events_30d,
    e.product_view_events_30d,
    e.add_to_cart_events_30d,
    e.remove_from_cart_events_30d,
    e.checkout_started_30d,
    e.payment_failed_30d,
    e.purchase_events_30d,
    CASE WHEN e.checkout_started_30d > 0
         THEN e.purchase_events_30d::numeric / e.checkout_started_30d
         ELSE NULL END AS checkout_conversion_rate_30d,
    o.orders_total_30d,
    o.orders_cancelled_refunded_30d,
    CASE WHEN o.orders_total_30d > 0
         THEN o.orders_cancelled_refunded_30d::numeric / o.orders_total_30d
         ELSE NULL END AS cancelled_refunded_rate_30d,
    n.notifications_sent_30d,
    n.notifications_opened_30d,
    CASE WHEN n.notifications_sent_30d > 0
         THEN n.notifications_opened_30d::numeric / n.notifications_sent_30d
         ELSE NULL END AS notification_open_rate_30d,
    r.avg_review_rating_30d,
    r.review_count_30d,
    (COALESCE(s.session_count_30d, 0) = 0 AND COALESCE(e.total_events_30d, 0) = 0) AS is_thin_history
FROM win w
JOIN public.users u ON u.user_id = w.user_id
LEFT JOIN sess_agg s ON s.user_id = w.user_id
LEFT JOIN event_agg e ON e.user_id = w.user_id
LEFT JOIN order_agg o ON o.user_id = w.user_id
LEFT JOIN notif_agg n ON n.user_id = w.user_id
LEFT JOIN review_agg r ON r.user_id = w.user_id;
