# Business Switching API Documentation

## Overview

This document describes the Business Context Switching feature that allows users to work with multiple businesses and switch between them seamlessly. All data displayed in the application is automatically filtered based on the user's active business context.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Database Changes](#database-changes)
3. [Authentication Changes](#authentication-changes)
4. [API Endpoints](#api-endpoints)
5. [Frontend Integration](#frontend-integration)
6. [Role-Based Behavior](#role-based-behavior)
7. [Testing Scenarios](#testing-scenarios)

---

## Architecture Overview

### How It Works

1. **User Login** → Returns all accessible businesses + sets default `active_business_id`
2. **JWT Token** → Contains `active_business_id` (embedded in token payload)
3. **Business Switch** → Updates active business + generates new token
4. **All GET Requests** → Automatically filter by active business (unless explicitly overridden)

### Key Concepts

- **Active Business**: The currently selected business context (stored in JWT token)
- **Flexible Filtering**: Endpoints accept optional `business_id` parameter to override active business
- **Role-Based Access**: Different roles have different data access patterns

---

## Database Changes

### New Column: `active_business_id`

```sql
-- Migration: Add active_business_id to users table
ALTER TABLE users
ADD COLUMN active_business_id INTEGER REFERENCES businesses(id);

-- Optional: Set default active_business_id for existing users
UPDATE users u
SET active_business_id = (
    SELECT business_id
    FROM user_business
    WHERE user_id = u.id
    LIMIT 1
)
WHERE active_business_id IS NULL;
```

### Updated User Model

```python
class User(AuditMixin, Base):
    __tablename__ = "users"
    # ... existing fields ...
    active_business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)

    # Relationships
    businesses = relationship("Business", secondary=user_business, back_populates="users")
    active_business = relationship("Business", foreign_keys=[active_business_id])
```

---

## Authentication Changes

### Updated JWT Token Payload

**Before:**

```json
{
  "sub": "08000000002",
  "role": "agent",
  "user_id": 123,
  "version": 1,
  "exp": 1706789400
}
```

**After:**

```json
{
  "sub": "08000000002",
  "role": "agent",
  "user_id": 123,
  "active_business_id": 100,
  "version": 1,
  "exp": 1706789400
}
```

### Updated Login Response

**Endpoint:** `POST /api/v1/auth/login`

**Request:**

```json
{
  "username": "08000000002",
  "pin": "1234"
}
```

**Response:**

```json
{
  "status": "success",
  "message": "Login successful",
  "data": {
    "user_id": 123,
    "full_name": "John Doe",
    "phone_number": "08000000002",
    "email": "john@example.com",
    "role": "agent",
    "is_active": true,
    "businesses": [
      {
        "id": 100,
        "name": "Business A",
        "unique_code": "BUS001",
        "address": "123 Main St",
        "units": [{ "id": 1, "name": "Unit 1", "location": "Location A" }]
      },
      {
        "id": 200,
        "name": "Business B",
        "unique_code": "BUS002",
        "address": "456 Oak Ave",
        "units": []
      }
    ],
    "active_business_id": 100,
    "created_at": "2024-01-15T10:30:00Z",
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "next_action": "choose_action"
  }
}
```

---

## API Endpoints

### 1. Switch Business Context

**Endpoint:** `POST /api/v1/auth/switch-business`

**Description:** Switch user's active business and receive a new JWT token.

**Authentication:** Required (Bearer token)

**Request Body:**

```json
{
  "business_id": 200
}
```

**Success Response (200):**

```json
{
  "status": "success",
  "message": "Business switched successfully",
  "data": {
    "user_id": 123,
    "full_name": "John Doe",
    "phone_number": "08000000002",
    "email": "john@example.com",
    "role": "agent",
    "is_active": true,
    "businesses": [...],
    "active_business_id": 200,
    "created_at": "2024-01-15T10:30:00Z",
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.NEW_TOKEN...",
    "next_action": "choose_action"
  }
}
```

**Error Responses:**

| Status | Message                                   | Description                               |
| ------ | ----------------------------------------- | ----------------------------------------- |
| 403    | "You do not have access to this business" | User doesn't belong to requested business |
| 404    | "User not found"                          | Invalid user                              |

---

### 2. Get All Savings Accounts

**Endpoint:** `GET /api/v1/savings`

**Description:** Get savings accounts with flexible business filtering.

**Authentication:** Required (Bearer token)

**Query Parameters:**

| Parameter      | Type    | Required | Default              | Description                 |
| -------------- | ------- | -------- | -------------------- | --------------------------- |
| `business_id`  | integer | No       | `active_business_id` | Filter by specific business |
| `customer_id`  | integer | No       | -                    | Filter by customer ID       |
| `unit_id`      | integer | No       | -                    | Filter by unit ID           |
| `savings_type` | string  | No       | -                    | "DAILY" or "TARGET"         |
| `limit`        | integer | No       | 10                   | Records per page (max: 100) |
| `offset`       | integer | No       | 0                    | Records to skip             |

**Business Selection Logic:**

1. If `business_id` provided → Use it (with validation)
2. Else use `active_business_id` from JWT token
3. Super admin with no `business_id` → Show all businesses

**Request Examples:**

```bash
# Use active business from token
GET /api/v1/savings?limit=10&offset=0

# Explicit business override
GET /api/v1/savings?business_id=200&limit=10

# Super admin - all businesses
GET /api/v1/savings?limit=50
```

---

## Frontend Integration

### 1. API Service

```typescript
// services/api.ts
const API_BASE_URL = "/api/v1";

class ApiService {
  private getAuthHeader(): HeadersInit {
    const token = localStorage.getItem("access_token");
    return {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    };
  }

  async login(username: string, pin: string) {
    const response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, pin }),
    });

    const data = await response.json();

    if (data.status === "success") {
      localStorage.setItem("access_token", data.data.access_token);
      localStorage.setItem(
        "active_business_id",
        data.data.active_business_id.toString()
      );
    }

    return data;
  }

  async switchBusiness(businessId: number) {
    const response = await fetch(`${API_BASE_URL}/auth/switch-business`, {
      method: "POST",
      headers: this.getAuthHeader(),
      body: JSON.stringify({ business_id: businessId }),
    });

    const data = await response.json();

    if (data.status === "success") {
      // CRITICAL: Update token with new one
      localStorage.setItem("access_token", data.data.access_token);
      localStorage.setItem("active_business_id", businessId.toString());
    }

    return data;
  }

  async getSavings(params?: {
    business_id?: number;
    limit?: number;
    offset?: number;
  }) {
    const queryParams = new URLSearchParams();
    if (params?.business_id)
      queryParams.append("business_id", params.business_id.toString());
    if (params?.limit) queryParams.append("limit", params.limit.toString());
    if (params?.offset) queryParams.append("offset", params.offset.toString());

    const response = await fetch(`${API_BASE_URL}/savings?${queryParams}`, {
      headers: this.getAuthHeader(),
    });

    return await response.json();
  }
}

export const apiService = new ApiService();
```

### 2. React Business Switcher Component

```tsx
// components/BusinessSwitcher.tsx
import React, { useState } from "react";
import { apiService } from "../services/api";

interface Business {
  id: number;
  name: string;
  unique_code: string;
}

export const BusinessSwitcher: React.FC<{
  businesses: Business[];
  onSwitch?: () => void;
}> = ({ businesses, onSwitch }) => {
  const [activeBusinessId, setActiveBusinessId] = useState<number>(() =>
    parseInt(localStorage.getItem("active_business_id") || "0")
  );
  const [loading, setLoading] = useState(false);

  const handleSwitch = async (businessId: number) => {
    if (businessId === activeBusinessId) return;

    setLoading(true);
    try {
      await apiService.switchBusiness(businessId);
      setActiveBusinessId(businessId);

      if (onSwitch) {
        await onSwitch();
      }
    } catch (error) {
      console.error("Failed to switch business:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="business-switcher">
      <select
        value={activeBusinessId}
        onChange={(e) => handleSwitch(parseInt(e.target.value))}
        disabled={loading}
      >
        {businesses.map((business) => (
          <option key={business.id} value={business.id}>
            {business.name} ({business.unique_code})
          </option>
        ))}
      </select>
      {loading && <span>Switching...</span>}
    </div>
  );
};
```

---

## Role-Based Behavior

### Customer Role

- **Login**: Sets active_business_id to first business
- **Switch**: Can switch between their businesses
- **Data**: Always filtered by active_business_id

### Agent / Sub-Agent Role

- **Login**: Sets active_business_id to first business
- **Switch**: Can switch between assigned businesses
- **Data**: Filtered by active_business_id, can override with `business_id` param

### Admin Role

- **Login**: May or may not have active_business_id
- **Switch**: Can switch to any business
- **Data**: Must provide business_id or use active_business_id

### Super Admin Role

- **Login**: No default active_business_id
- **Switch**: Can switch to any business (optional)
- **Data**: No business specified → Shows ALL businesses

---

## Testing Scenarios

### Scenario 1: Customer with Multiple Businesses

1. Login as customer with 2 businesses
2. Verify `active_business_id` is set to first business
3. View savings → Should see only Business A savings
4. Switch to Business B
5. View savings → Should see only Business B savings

### Scenario 2: Agent Switching Businesses

1. Login as agent with Business A and Business B
2. View customers → Should see Business A customers
3. Switch to Business B
4. View customers → Should see Business B customers

### Scenario 3: Super Admin Global View

1. Login as super_admin
2. View all savings without business_id → Should see ALL businesses
3. Filter by business: `GET /savings?business_id=100`
4. Should see only Business 100 savings

---

## Best Practices

### Backend

1. **Always validate business access** before filtering data
2. **Use active_business_id as default**, allow explicit override
3. **Include context in responses** to help frontend debugging
4. **Log business switches** for audit trail

### Frontend

1. **Always replace token** after switching
2. **Refresh all data** after switch
3. **Show loading states** during switch
4. **Handle errors gracefully**

---

**Last Updated:** January 2025  
**Version:** 1.0.0
