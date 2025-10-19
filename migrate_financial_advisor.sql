-- Migration: Add Financial Advisor Tables
-- Date: 2025-10-19
-- Description: Creates tables for savings goals, financial health scores, spending patterns, and notifications

-- Create enum types (safe to run multiple times)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'goalpriority') THEN
        CREATE TYPE goalpriority AS ENUM ('high', 'medium', 'low');
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'goalstatus') THEN
        CREATE TYPE goalstatus AS ENUM ('active', 'achieved', 'abandoned');
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'patterntype') THEN
        CREATE TYPE patterntype AS ENUM ('recurring', 'seasonal', 'anomaly');
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'notificationtype') THEN
        CREATE TYPE notificationtype AS ENUM ('overspending', 'goal_progress', 'spending_anomaly', 'savings_opportunity', 'monthly_summary', 'health_score');
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'notificationpriority') THEN
        CREATE TYPE notificationpriority AS ENUM ('high', 'medium', 'low');
    END IF;
END $$;

-- Create savings_goals table
CREATE TABLE IF NOT EXISTS savings_goals (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    target_amount NUMERIC(10, 2) NOT NULL,
    current_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    deadline DATE,
    priority goalpriority NOT NULL DEFAULT 'medium',
    category VARCHAR(50),
    status goalstatus NOT NULL DEFAULT 'active',
    is_ai_recommended BOOLEAN NOT NULL DEFAULT false,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by INTEGER,
    updated_by INTEGER
);

-- Create indexes for savings_goals
CREATE INDEX IF NOT EXISTS ix_savings_goals_customer_id ON savings_goals(customer_id);
CREATE INDEX IF NOT EXISTS ix_savings_goals_status ON savings_goals(status);

-- Create financial_health_scores table
CREATE TABLE IF NOT EXISTS financial_health_scores (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score INTEGER NOT NULL,
    score_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    factors_breakdown JSONB NOT NULL,
    recommendations JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by INTEGER,
    updated_by INTEGER
);

-- Create indexes for financial_health_scores
CREATE INDEX IF NOT EXISTS ix_health_scores_customer_id ON financial_health_scores(customer_id);
CREATE INDEX IF NOT EXISTS ix_health_scores_score_date ON financial_health_scores(score_date);

-- Create spending_patterns table
CREATE TABLE IF NOT EXISTS spending_patterns (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pattern_type patterntype NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(10, 2),
    frequency VARCHAR(50),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_occurrence DATE,
    pattern_metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by INTEGER,
    updated_by INTEGER
);

-- Create indexes for spending_patterns
CREATE INDEX IF NOT EXISTS ix_spending_patterns_customer_id ON spending_patterns(customer_id);
CREATE INDEX IF NOT EXISTS ix_spending_patterns_type ON spending_patterns(pattern_type);

-- Create user_notifications table
CREATE TABLE IF NOT EXISTS user_notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notification_type notificationtype NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    priority notificationpriority NOT NULL DEFAULT 'medium',
    is_read BOOLEAN NOT NULL DEFAULT false,
    related_entity_id INTEGER,
    related_entity_type VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    created_by INTEGER,
    updated_by INTEGER
);

-- Create indexes for user_notifications
CREATE INDEX IF NOT EXISTS ix_user_notifications_user_id ON user_notifications(user_id);
CREATE INDEX IF NOT EXISTS ix_user_notifications_is_read ON user_notifications(is_read);
CREATE INDEX IF NOT EXISTS ix_user_notifications_created_at ON user_notifications(created_at);

-- Verification queries
SELECT 'savings_goals table created' as status, COUNT(*) as count FROM savings_goals;
SELECT 'financial_health_scores table created' as status, COUNT(*) as count FROM financial_health_scores;
SELECT 'spending_patterns table created' as status, COUNT(*) as count FROM spending_patterns;
SELECT 'user_notifications table created' as status, COUNT(*) as count FROM user_notifications;

