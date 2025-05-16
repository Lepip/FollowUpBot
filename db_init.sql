CREATE TABLE IF NOT EXISTS public.convs
(
    chat_id bigint NOT NULL,
    is_started boolean NOT NULL DEFAULT FALSE,
    is_concluded boolean NOT NULL DEFAULT FALSE,
    has_questions boolean NOT NULL DEFAULT FALSE,
    set_theme boolean NOT NULL DEFAULT FALSE,
    stage_id integer NOT NULL,
    batch_id integer NOT NULL
);

CREATE TABLE IF NOT EXISTS public.chatlogs
(
    chat_id bigint NOT NULL,
    message_id bigint NOT NULL,
    message_text text NOT NULL,
    role text NOT NULL
);