/* sql_id: create_consultations_table */
CREATE TABLE IF NOT EXISTS consultations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id),
    employee_id UUID NOT NULL REFERENCES employees(id),
    house_view_id UUID REFERENCES house_views(id),
    consultation_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    channel_code VARCHAR(30) NOT NULL CHECK (channel_code IN ('FACE_TO_FACE', 'PHONE', 'VIDEO', 'WRITTEN')),
    status_code VARCHAR(30) NOT NULL CHECK (status_code IN ('DRAFT', 'SAVED', 'COMPLETED')),
    summary TEXT,
    suitability_checked BOOLEAN NOT NULL DEFAULT FALSE,
    explanation_checked BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT consultations_complete_checks CHECK (
        status_code <> 'COMPLETED' OR (suitability_checked IS TRUE AND explanation_checked IS TRUE)
    )
);

/* sql_id: index_consultations_customer */
CREATE INDEX IF NOT EXISTS idx_consultations_customer ON consultations(customer_id);

/* sql_id: index_consultations_employee */
CREATE INDEX IF NOT EXISTS idx_consultations_employee ON consultations(employee_id, created_at DESC);

/* sql_id: create_consultation_notes_table */
CREATE TABLE IF NOT EXISTS consultation_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consultation_id UUID NOT NULL REFERENCES consultations(id),
    author_id UUID NOT NULL REFERENCES employees(id),
    note_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_consultation_notes_consultation */
CREATE INDEX IF NOT EXISTS idx_consultation_notes_consultation ON consultation_notes(consultation_id, created_at DESC);

/* sql_id: add_house_view_application_consultation_fk */
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'house_view_applications_consultation_id_fkey'
    ) THEN
        ALTER TABLE house_view_applications
            ADD CONSTRAINT house_view_applications_consultation_id_fkey
            FOREIGN KEY (consultation_id) REFERENCES consultations(id);
    END IF;
END
$$;
