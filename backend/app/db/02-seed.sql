-- Idempotent demo data (DELETE + re-insert so tests are deterministic).
DELETE FROM thread_events;
DELETE FROM threads;
DELETE FROM feedback;
DELETE FROM refund_events;
DELETE FROM invoices;
DELETE FROM subscriptions;
DELETE FROM customers;

INSERT INTO customers (id, name, email, billing_email) VALUES
('cus_001', 'Priya Sharma',   'priya@example.com',  'billing.priya@example.com'),
('cus_002', 'Marcus Chen',    'marcus@example.com', 'marcus@example.com'),
('cus_003', 'Aisha Okafor',   'aisha@example.com',  'aisha@example.com'),
('cus_004', 'Tom Contractor', 'tom@example.com',    'tom@example.com'),
('cus_005', 'Lena Small',     'lena@example.com',   'lena@example.com');

INSERT INTO subscriptions (id, customer_id, tier, status, monthly_cents, period_start, period_end) VALUES
('sub_001', 'cus_001', 'pro',      'active',   7900, DATE '2026-10-01', DATE '2026-10-31'),
('sub_002', 'cus_002', 'pro',      'active',   7900, DATE '2026-10-01', DATE '2026-10-31'),
('sub_003', 'cus_003', 'starter',  'past_due', 2900, DATE '2026-10-01', DATE '2026-10-31'),
('sub_004', 'cus_004', 'starter',  'active',   2900, DATE '2026-10-01', DATE '2026-10-31'),
('sub_005', 'cus_005', 'starter',  'active',   2900, DATE '2026-10-01', DATE '2026-10-31');

INSERT INTO invoices (id, customer_id, amount_cents, status, period_start, period_end) VALUES
('in_1001', 'cus_001', 7900, 'paid',     DATE '2026-10-01', DATE '2026-10-31'),
('in_1002', 'cus_001', 7900, 'paid',     DATE '2026-10-01', DATE '2026-10-31'),  -- duplicate of in_1001
('in_2001', 'cus_002', 7900, 'paid',     DATE '2026-10-01', DATE '2026-10-31'),
('in_3001', 'cus_003', 2900, 'past_due', DATE '2026-10-01', DATE '2026-10-31'),
('in_4001', 'cus_004', 2900, 'paid',     DATE '2026-10-01', DATE '2026-10-31'),
('in_5001', 'cus_005', 2900, 'paid',     DATE '2026-10-01', DATE '2026-10-31');  -- small refund scenario
