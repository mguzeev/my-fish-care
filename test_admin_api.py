#!/usr/bin/env python3
"""Test script for admin API improvements."""

import asyncio
import aiohttp
import json

BASE_URL = "http://localhost:8765"
AUTH_TOKEN = "test_admin_token"  # Replace with actual admin token

async def test_admin_api():
    """Test the admin API endpoints."""
    
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
        
        print("🧪 Testing Admin API improvements...")
        print("=" * 50)
        
        # Test dashboard stats
        try:
            async with session.get(f"{BASE_URL}/admin/dashboard/stats", headers=headers) as resp:
                if resp.status == 200:
                    stats = await resp.json()
                    print("✅ Dashboard stats:")
                    print(f"   Total Users: {stats.get('total_users', 0)}")
                    print(f"   Active Subscriptions: {stats.get('active_subscriptions', 0)}")
                    print(f"   Revenue Total: ${stats.get('revenue_total', 0)}")
                    print(f"   Revenue Active: ${stats.get('revenue_active', 0)}")
                    print(f"   Subscription Plans: {stats.get('subscription_plans_count', 0)}")
                    print(f"   Credit Plans: {stats.get('one_time_plans_count', 0)}")
                else:
                    print(f"❌ Dashboard stats failed: {resp.status}")
        except Exception as e:
            print(f"❌ Dashboard error: {e}")
        
        print()
        
        # Test plans list
        try:
            async with session.get(f"{BASE_URL}/admin/plans", headers=headers) as resp:
                if resp.status == 200:
                    plans = await resp.json()
                    print("✅ Plans list:")
                    for plan in plans:
                        plan_type = plan.get('plan_type', 'UNKNOWN')
                        is_default = "✓" if plan.get('is_default') else ""
                        agents = plan.get('agent_count', 0)
                        if plan_type == 'ONE_TIME':
                            limit_info = f"{plan.get('one_time_limit', 0)} uses"
                        else:
                            limit_info = f"{plan.get('max_requests_per_interval', 0)} req/{plan.get('interval', 'month')}"
                        print(f"   [{plan['id']}] {plan['name']} - {plan_type} - ${plan['price']} - {limit_info} - {agents} agents {is_default}")
                else:
                    print(f"❌ Plans list failed: {resp.status}")
        except Exception as e:
            print(f"❌ Plans error: {e}")
        
        print()
        
        # Test creating a ONE_TIME plan
        try:
            new_plan = {
                "name": "Test Credit Pack",
                "plan_type": "ONE_TIME", 
                "price": 5.00,
                "interval": "MONTHLY",  # Will be ignored for ONE_TIME
                "one_time_limit": 50,
                "currency": "USD",
                "max_requests_per_interval": 1,  # Default for ONE_TIME
                "max_tokens_per_request": 2000,
                "free_requests_limit": 0,
                "free_trial_days": 0,
                "is_default": False,
                "has_api_access": False,
                "has_priority_support": False, 
                "has_advanced_analytics": False
            }
            
            async with session.post(f"{BASE_URL}/admin/plans", headers=headers, json=new_plan) as resp:
                if resp.status == 200:
                    created_plan = await resp.json()
                    print("✅ Created ONE_TIME plan:")
                    print(f"   ID: {created_plan['id']}")
                    print(f"   Type: {created_plan['plan_type']}")
                    print(f"   Credits: {created_plan['one_time_limit']}")
                    
                    # Test updating the plan
                    update_data = {**new_plan, "name": "Updated Credit Pack", "one_time_limit": 75}
                    plan_id = created_plan['id']
                    
                    async with session.put(f"{BASE_URL}/admin/plans/{plan_id}", headers=headers, json=update_data) as update_resp:
                        if update_resp.status == 200:
                            updated_plan = await update_resp.json()
                            print("✅ Updated plan:")
                            print(f"   Name: {updated_plan['name']}")
                            print(f"   Credits: {updated_plan['one_time_limit']}")
                        else:
                            print(f"❌ Plan update failed: {update_resp.status}")
                    
                    # Clean up - delete test plan
                    async with session.delete(f"{BASE_URL}/admin/plans/{plan_id}", headers=headers) as delete_resp:
                        if delete_resp.status == 200:
                            print("✅ Cleaned up test plan")
                        else:
                            print(f"⚠️ Failed to delete test plan: {delete_resp.status}")
                            
                else:
                    error_text = await resp.text()
                    print(f"❌ Plan creation failed: {resp.status}")
                    print(f"   Error: {error_text}")
        except Exception as e:
            print(f"❌ Plan creation error: {e}")
        
        print()
        print("🎉 Admin API test complete!")

if __name__ == "__main__":
    asyncio.run(test_admin_api())