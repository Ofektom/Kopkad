#!/bin/bash

# Expense Creation Endpoint Test Script
# Make this executable: chmod +x test_expense_creation.sh
# Run with: ./tests/test_expense_creation.sh

# Configuration
BASE_URL="https://kopkad.onrender.com"
API_BASE="${BASE_URL}/api/v1"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test user credentials (UPDATE THESE!)
TEST_EMAIL="test@example.com"
TEST_PASSWORD="your_password"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}EXPENSE CREATION ENDPOINT TESTS${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Step 1: Login and get access token
echo -e "${YELLOW}Step 1: Logging in...${NC}"
LOGIN_RESPONSE=$(curl -s -X POST "${API_BASE}/users/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"${TEST_EMAIL}\",
    \"password\": \"${TEST_PASSWORD}\"
  }")

ACCESS_TOKEN=$(echo $LOGIN_RESPONSE | jq -r '.data.access_token')

if [ "$ACCESS_TOKEN" = "null" ] || [ -z "$ACCESS_TOKEN" ]; then
  echo -e "${RED}❌ Login failed!${NC}"
  echo $LOGIN_RESPONSE | jq '.'
  exit 1
fi

echo -e "${GREEN}✅ Login successful!${NC}"
echo -e "Access Token: ${ACCESS_TOKEN:0:20}...\n"

# Set authorization header
AUTH_HEADER="Authorization: Bearer $ACCESS_TOKEN"

# Test 1: Create SALARY expense card
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Test 1: Create SALARY Expense Card${NC}"
echo -e "${BLUE}========================================${NC}"
SALARY_RESPONSE=$(curl -s -X POST "${API_BASE}/expenses/card" \
  -H "Content-Type: application/json" \
  -H "$AUTH_HEADER" \
  -d '{
    "name": "November Salary Card",
    "income_type": "SALARY",
    "initial_income": 150000.00
  }')

echo "$SALARY_RESPONSE" | jq '.'
SALARY_CARD_ID=$(echo $SALARY_RESPONSE | jq -r '.id // empty')
if [ ! -z "$SALARY_CARD_ID" ]; then
  echo -e "${GREEN}✅ Salary card created! ID: $SALARY_CARD_ID${NC}\n"
else
  echo -e "${RED}❌ Failed to create salary card${NC}\n"
fi

# Test 2: Create BUSINESS expense card
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Test 2: Create BUSINESS Expense Card${NC}"
echo -e "${BLUE}========================================${NC}"
BUSINESS_RESPONSE=$(curl -s -X POST "${API_BASE}/expenses/card" \
  -H "Content-Type: application/json" \
  -H "$AUTH_HEADER" \
  -d '{
    "name": "Business Revenue - November",
    "income_type": "BUSINESS",
    "initial_income": 500000.00
  }')

echo "$BUSINESS_RESPONSE" | jq '.'
BUSINESS_CARD_ID=$(echo $BUSINESS_RESPONSE | jq -r '.id // empty')
if [ ! -z "$BUSINESS_CARD_ID" ]; then
  echo -e "${GREEN}✅ Business card created! ID: $BUSINESS_CARD_ID${NC}\n"
else
  echo -e "${RED}❌ Failed to create business card${NC}\n"
fi

# Test 3: Create BORROWED expense card
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Test 3: Create BORROWED Expense Card${NC}"
echo -e "${BLUE}========================================${NC}"
BORROWED_RESPONSE=$(curl -s -X POST "${API_BASE}/expenses/card" \
  -H "Content-Type: application/json" \
  -H "$AUTH_HEADER" \
  -d '{
    "name": "Loan for Business Expansion",
    "income_type": "BORROWED",
    "initial_income": 200000.00
  }')

echo "$BORROWED_RESPONSE" | jq '.'
BORROWED_CARD_ID=$(echo $BORROWED_RESPONSE | jq -r '.id // empty')
if [ ! -z "$BORROWED_CARD_ID" ]; then
  echo -e "${GREEN}✅ Borrowed card created! ID: $BORROWED_CARD_ID${NC}\n"
else
  echo -e "${RED}❌ Failed to create borrowed card${NC}\n"
fi

# Test 4: Create OTHER expense card
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Test 4: Create OTHER Expense Card${NC}"
echo -e "${BLUE}========================================${NC}"
OTHER_RESPONSE=$(curl -s -X POST "${API_BASE}/expenses/card" \
  -H "Content-Type: application/json" \
  -H "$AUTH_HEADER" \
  -d '{
    "name": "Freelance Project Income",
    "income_type": "OTHER",
    "initial_income": 75000.00,
    "income_details": "Web development project for Client XYZ"
  }')

echo "$OTHER_RESPONSE" | jq '.'
OTHER_CARD_ID=$(echo $OTHER_RESPONSE | jq -r '.id // empty')
if [ ! -z "$OTHER_CARD_ID" ]; then
  echo -e "${GREEN}✅ Other card created! ID: $OTHER_CARD_ID${NC}\n"
else
  echo -e "${RED}❌ Failed to create other card${NC}\n"
fi

# Test 5: Get eligible savings
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Test 5: Get Eligible Savings${NC}"
echo -e "${BLUE}========================================${NC}"
SAVINGS_RESPONSE=$(curl -s -X GET "${API_BASE}/expenses/eligible-savings" \
  -H "$AUTH_HEADER")

echo "$SAVINGS_RESPONSE" | jq '.'
SAVINGS_ID=$(echo $SAVINGS_RESPONSE | jq -r '.data.savings[0].id // empty')
if [ ! -z "$SAVINGS_ID" ]; then
  echo -e "${GREEN}✅ Found eligible savings! ID: $SAVINGS_ID${NC}\n"
  
  # Test 6: Create SAVINGS expense card
  echo -e "${BLUE}========================================${NC}"
  echo -e "${YELLOW}Test 6: Create SAVINGS Expense Card${NC}"
  echo -e "${BLUE}========================================${NC}"
  SAVINGS_CARD_RESPONSE=$(curl -s -X POST "${API_BASE}/expenses/card" \
    -H "Content-Type: application/json" \
    -H "$AUTH_HEADER" \
    -d "{
      \"name\": \"Expense Card from Savings Payout\",
      \"income_type\": \"SAVINGS\",
      \"savings_id\": $SAVINGS_ID
    }")
  
  echo "$SAVINGS_CARD_RESPONSE" | jq '.'
  SAVINGS_CARD_ID=$(echo $SAVINGS_CARD_RESPONSE | jq -r '.id // empty')
  if [ ! -z "$SAVINGS_CARD_ID" ]; then
    echo -e "${GREEN}✅ Savings card created! ID: $SAVINGS_CARD_ID${NC}\n"
  else
    echo -e "${RED}❌ Failed to create savings card${NC}\n"
  fi
else
  echo -e "${YELLOW}⚠️  No eligible savings found${NC}\n"
fi

# Test 7: Create Planner Card
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Test 7: Create Planner Card${NC}"
echo -e "${BLUE}========================================${NC}"
PLANNER_RESPONSE=$(curl -s -X POST "${API_BASE}/expenses/planner/create" \
  -H "Content-Type: application/json" \
  -H "$AUTH_HEADER" \
  -d '{
    "name": "December Budget Plan",
    "capital": 250000.00,
    "planned_expenses": [
      {
        "category": "RENT",
        "amount": 80000.00,
        "purpose": "Monthly apartment rent"
      },
      {
        "category": "FOOD",
        "amount": 50000.00,
        "purpose": "Groceries and meal prep"
      },
      {
        "category": "TRANSPORT",
        "amount": 30000.00,
        "purpose": "Fuel and transportation"
      },
      {
        "category": "UTILITIES",
        "amount": 25000.00,
        "purpose": "Electricity, water, internet"
      },
      {
        "category": "ENTERTAINMENT",
        "amount": 20000.00,
        "purpose": "Movies, outings, recreation"
      },
      {
        "category": "MISC",
        "amount": 15000.00,
        "purpose": "Emergency fund and miscellaneous"
      }
    ]
  }')

echo "$PLANNER_RESPONSE" | jq '.'
PLANNER_CARD_ID=$(echo $PLANNER_RESPONSE | jq -r '.card.id // empty')
if [ ! -z "$PLANNER_CARD_ID" ]; then
  echo -e "${GREEN}✅ Planner card created! ID: $PLANNER_CARD_ID${NC}\n"
else
  echo -e "${RED}❌ Failed to create planner card${NC}\n"
fi

# Test 8: Record expense on first card
if [ ! -z "$SALARY_CARD_ID" ]; then
  echo -e "${BLUE}========================================${NC}"
  echo -e "${YELLOW}Test 8: Record Expense on Card${NC}"
  echo -e "${BLUE}========================================${NC}"
  EXPENSE_RESPONSE=$(curl -s -X POST "${API_BASE}/expenses/card/${SALARY_CARD_ID}/expense" \
    -H "Content-Type: application/json" \
    -H "$AUTH_HEADER" \
    -d "{
      \"category\": \"FOOD\",
      \"description\": \"Lunch at restaurant\",
      \"amount\": 5500.00,
      \"date\": \"$(date +%Y-%m-%d)\"
    }")
  
  echo "$EXPENSE_RESPONSE" | jq '.'
  EXPENSE_ID=$(echo $EXPENSE_RESPONSE | jq -r '.id // empty')
  if [ ! -z "$EXPENSE_ID" ]; then
    echo -e "${GREEN}✅ Expense recorded! ID: $EXPENSE_ID${NC}\n"
  else
    echo -e "${RED}❌ Failed to record expense${NC}\n"
  fi
fi

# Test 9: Get all expense cards
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Test 9: Get All Expense Cards${NC}"
echo -e "${BLUE}========================================${NC}"
CARDS_RESPONSE=$(curl -s -X GET "${API_BASE}/expenses/cards?limit=20&offset=0" \
  -H "$AUTH_HEADER")

echo "$CARDS_RESPONSE" | jq '.'
CARDS_COUNT=$(echo $CARDS_RESPONSE | jq -r '.data.cards | length')
echo -e "${GREEN}✅ Retrieved $CARDS_COUNT expense cards${NC}\n"

# Test 10: Get expense metrics
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}Test 10: Get Expense Metrics${NC}"
echo -e "${BLUE}========================================${NC}"
METRICS_RESPONSE=$(curl -s -X GET "${API_BASE}/expenses/metrics" \
  -H "$AUTH_HEADER")

echo "$METRICS_RESPONSE" | jq '.'
echo -e "${GREEN}✅ Metrics retrieved${NC}\n"

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}TEST SUMMARY${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Salary Card ID: ${SALARY_CARD_ID:-Not created}"
echo -e "Business Card ID: ${BUSINESS_CARD_ID:-Not created}"
echo -e "Borrowed Card ID: ${BORROWED_CARD_ID:-Not created}"
echo -e "Other Card ID: ${OTHER_CARD_ID:-Not created}"
echo -e "Savings Card ID: ${SAVINGS_CARD_ID:-Not created}"
echo -e "Planner Card ID: ${PLANNER_CARD_ID:-Not created}"
echo -e "\n${GREEN}✅ All tests completed!${NC}"

