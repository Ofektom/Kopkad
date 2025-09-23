-- Set search_path to public
SET search_path TO public;

-- Drop enums if they exist
DROP TYPE IF EXISTS income_type CASCADE;
DROP TYPE IF EXISTS expensecategory CASCADE;

-- Create enums
CREATE TYPE income_type AS ENUM ('SALARY', 'SAVINGS', 'BORROWED', 'BUSINESS', 'OTHER');
CREATE TYPE expensecategory AS ENUM ('FOOD', 'TRANSPORT', 'ENTERTAINMENT', 'UTILITIES', 'RENT', 'MISC');

-- Create expense_cards table
CREATE TABLE expense_cards (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    income_type income_type NOT NULL,
    income_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    balance NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    savings_id INTEGER,
    income_details VARCHAR(255),
    created_by INTEGER,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_by INTEGER,
    updated_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (customer_id) REFERENCES users(id),
    FOREIGN KEY (savings_id) REFERENCES savings_accounts(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
);

-- Create expenses table
CREATE TABLE expenses (
    id SERIAL PRIMARY KEY,
    expense_card_id INTEGER NOT NULL,
    category expensecategory,
    description VARCHAR(255),
    amount NUMERIC(10, 2) NOT NULL,
    date DATE NOT NULL,
    created_by INTEGER,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_by INTEGER,
    updated_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (expense_card_id) REFERENCES expense_cards(id),
    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL
);