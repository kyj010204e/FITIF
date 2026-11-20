CREATE TABLE IF NOT EXISTS public.stress_checkin (
    member_id integer NOT NULL REFERENCES public.member(member_id) ON DELETE CASCADE,
    recorded_on date NOT NULL,
    score smallint NOT NULL CHECK (score BETWEEN 1 AND 5),
    recorded_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (member_id, recorded_on)
);
