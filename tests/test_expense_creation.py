"""
Test script for expense creation endpoints
Run with: python tests/test_expense_creation.py
"""

import requests
import json
from datetime import date, datetime, timedelta
from decimal import Decimal

# Configuration
BASE_URL = "https://kopkad.onrender.com"  # Update with your actual URL
API_BASE = f"{BASE_URL}/api/v1"

# Add your test user credentials
TEST_USER_EMAIL = "test@example.com"
TEST_USER_PASSWORD = "your_password"

class ExpenseTestRunner:
    def __init__(self):
        self.access_token = None
        self.headers = {}
        self.created_card_ids = []
        
    def login(self):
        """Login and get access token"""
        print("\n" + "="*60)
        print("LOGGING IN...")
        print("="*60)
        
        response = requests.post(
            f"{API_BASE}/users/login",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            self.access_token = data.get("data", {}).get("access_token")
            self.headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            print("✅ Login successful!")
            return True
        else:
            print(f"❌ Login failed: {response.status_code}")
            print(response.text)
            return False
    
    def test_create_external_salary_card(self):
        """Test 1: Create expense card with SALARY income"""
        print("\n" + "="*60)
        print("TEST 1: Create Expense Card (SALARY)")
        print("="*60)
        
        payload = {
            "name": "November Salary Card",
            "income_type": "SALARY",
            "initial_income": 150000.00,
            # business_id is optional - will use active business
        }
        
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            f"{API_BASE}/expenses/card",
            headers=self.headers,
            json=payload
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            card_id = response.json().get("id")
            self.created_card_ids.append(card_id)
            print(f"✅ Expense card created successfully! ID: {card_id}")
            return card_id
        else:
            print(f"❌ Failed to create expense card")
            return None
    
    def test_create_business_income_card(self):
        """Test 2: Create expense card with BUSINESS income"""
        print("\n" + "="*60)
        print("TEST 2: Create Expense Card (BUSINESS)")
        print("="*60)
        
        payload = {
            "name": "Business Revenue - November",
            "income_type": "BUSINESS",
            "initial_income": 500000.00,
        }
        
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            f"{API_BASE}/expenses/card",
            headers=self.headers,
            json=payload
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            card_id = response.json().get("id")
            self.created_card_ids.append(card_id)
            print(f"✅ Business income card created! ID: {card_id}")
            return card_id
        else:
            print(f"❌ Failed to create business income card")
            return None
    
    def test_create_borrowed_income_card(self):
        """Test 3: Create expense card with BORROWED income"""
        print("\n" + "="*60)
        print("TEST 3: Create Expense Card (BORROWED)")
        print("="*60)
        
        payload = {
            "name": "Loan for Business Expansion",
            "income_type": "BORROWED",
            "initial_income": 200000.00,
        }
        
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            f"{API_BASE}/expenses/card",
            headers=self.headers,
            json=payload
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            card_id = response.json().get("id")
            self.created_card_ids.append(card_id)
            print(f"✅ Borrowed income card created! ID: {card_id}")
            return card_id
        else:
            print(f"❌ Failed to create borrowed income card")
            return None
    
    def test_create_other_income_card(self):
        """Test 4: Create expense card with OTHER income type"""
        print("\n" + "="*60)
        print("TEST 4: Create Expense Card (OTHER)")
        print("="*60)
        
        payload = {
            "name": "Freelance Project Income",
            "income_type": "OTHER",
            "initial_income": 75000.00,
            "income_details": "Web development project for Client XYZ"
        }
        
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            f"{API_BASE}/expenses/card",
            headers=self.headers,
            json=payload
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            card_id = response.json().get("id")
            self.created_card_ids.append(card_id)
            print(f"✅ Other income card created! ID: {card_id}")
            return card_id
        else:
            print(f"❌ Failed to create other income card")
            return None
    
    def test_get_eligible_savings(self):
        """Test 5: Get eligible savings accounts"""
        print("\n" + "="*60)
        print("TEST 5: Get Eligible Savings Accounts")
        print("="*60)
        
        response = requests.get(
            f"{API_BASE}/expenses/eligible-savings",
            headers=self.headers
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            savings_list = response.json().get("data", {}).get("savings", [])
            print(f"✅ Found {len(savings_list)} eligible savings accounts")
            return savings_list
        else:
            print(f"❌ Failed to get eligible savings")
            return []
    
    def test_create_savings_based_card(self, savings_id):
        """Test 6: Create expense card from completed savings"""
        print("\n" + "="*60)
        print("TEST 6: Create Expense Card from Savings")
        print("="*60)
        
        payload = {
            "name": "Expense Card from Savings Payout",
            "income_type": "SAVINGS",
            "savings_id": savings_id
        }
        
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            f"{API_BASE}/expenses/card",
            headers=self.headers,
            json=payload
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            card_id = response.json().get("id")
            self.created_card_ids.append(card_id)
            print(f"✅ Savings-based card created! ID: {card_id}")
            return card_id
        else:
            print(f"❌ Failed to create savings-based card")
            return None
    
    def test_create_planner_card(self):
        """Test 7: Create planner card with planned expenses"""
        print("\n" + "="*60)
        print("TEST 7: Create Planner Card with Planned Expenses")
        print("="*60)
        
        payload = {
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
        }
        
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            f"{API_BASE}/expenses/planner/create",
            headers=self.headers,
            json=payload
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            card_data = response.json().get("card", {})
            card_id = card_data.get("id")
            self.created_card_ids.append(card_id)
            print(f"✅ Planner card created! ID: {card_id}")
            print(f"AI Advice: {response.json().get('ai_advice', 'N/A')}")
            return card_id
        else:
            print(f"❌ Failed to create planner card")
            return None
    
    def test_record_expense(self, card_id):
        """Test 8: Record an expense on an existing card"""
        if not card_id:
            print("\n⚠️  Skipping test_record_expense - no card_id provided")
            return
        
        print("\n" + "="*60)
        print(f"TEST 8: Record Expense on Card {card_id}")
        print("="*60)
        
        payload = {
            "category": "FOOD",
            "description": "Lunch at restaurant",
            "amount": 5500.00,
            "date": date.today().isoformat()
        }
        
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(
            f"{API_BASE}/expenses/card/{card_id}/expense",
            headers=self.headers,
            json=payload
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print(f"✅ Expense recorded successfully!")
        else:
            print(f"❌ Failed to record expense")
    
    def test_get_expense_cards(self):
        """Test 9: Get all expense cards"""
        print("\n" + "="*60)
        print("TEST 9: Get All Expense Cards")
        print("="*60)
        
        response = requests.get(
            f"{API_BASE}/expenses/cards?limit=20&offset=0",
            headers=self.headers
        )
        
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        if response.status_code == 200:
            cards = data.get("data", {}).get("cards", [])
            print(f"✅ Retrieved {len(cards)} expense cards")
        else:
            print(f"❌ Failed to get expense cards")
    
    def test_get_expense_metrics(self):
        """Test 10: Get expense metrics"""
        print("\n" + "="*60)
        print("TEST 10: Get Expense Metrics")
        print("="*60)
        
        response = requests.get(
            f"{API_BASE}/expenses/metrics",
            headers=self.headers
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print(f"✅ Expense metrics retrieved successfully!")
        else:
            print(f"❌ Failed to get expense metrics")
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("\n" + "="*70)
        print("EXPENSE CREATION ENDPOINT TESTS")
        print("="*70)
        
        if not self.login():
            print("\n❌ Cannot proceed without authentication")
            return
        
        # Test external income cards
        salary_card_id = self.test_create_external_salary_card()
        business_card_id = self.test_create_business_income_card()
        borrowed_card_id = self.test_create_borrowed_income_card()
        other_card_id = self.test_create_other_income_card()
        
        # Test savings-based card
        eligible_savings = self.test_get_eligible_savings()
        if eligible_savings:
            savings_id = eligible_savings[0].get("id")
            self.test_create_savings_based_card(savings_id)
        else:
            print("\n⚠️  No eligible savings found - skipping savings-based card test")
        
        # Test planner card
        planner_card_id = self.test_create_planner_card()
        
        # Test recording expense
        if salary_card_id:
            self.test_record_expense(salary_card_id)
        
        # Test retrieval endpoints
        self.test_get_expense_cards()
        self.test_get_expense_metrics()
        
        # Summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Total cards created: {len(self.created_card_ids)}")
        print(f"Card IDs: {self.created_card_ids}")
        print("\n✅ All tests completed!")


if __name__ == "__main__":
    # Update these with your actual credentials
    print("\n⚠️  IMPORTANT: Update TEST_USER_EMAIL and TEST_USER_PASSWORD before running!")
    print("Update BASE_URL if testing locally\n")
    
    runner = ExpenseTestRunner()
    runner.run_all_tests()

