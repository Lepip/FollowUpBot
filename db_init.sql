CREATE TABLE IF NOT EXISTS public.convs
(
    chat_id bigint NOT NULL,
    conv_id bigint NOT NULL,
    conv_name text NOT NULL,
    is_current boolean NOT NULL DEFAULT FALSE,
    is_started boolean NOT NULL DEFAULT FALSE,
    is_concluded boolean NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS public.chatlogs
(
    conv_id bigint NOT NULL,
    message_id bigint NOT NULL,
    message_text text NOT NULL,
    role text NOT NULL
);

CREATE TABLE IF NOT EXISTS public.questions
(
    conv_id bigint NOT NULL,
    question_id bigint NOT NULL,
    question_text text NOT NULL,
    answer text
);

CREATE SEQUENCE conv_id_seq START 1;