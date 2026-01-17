#!/usr/bin/env python3
"""
Script to fix the PlanType enum values in the database.

This script converts lowercase plan_type values to uppercase to match
what SQLAlchemy enum expects:
- 'subscription' -> 'SUBSCRIPTION'  
- 'one_time' -> 'ONE_TIME'

Usage: python fix_plan_type_enum.py [database_path]
Default database path: bot.db
"""

import sqlite3
import sys
from pathlib import Path


def fix_plan_type_enum(db_path="bot.db"):
    """Fix the plan_type enum values in the database."""
    
    # Check if database exists
    if not Path(db_path).exists():
        print(f"Error: Database file '{db_path}' not found.")
        return False
    
    print(f"Connecting to database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # First, check current values
        print("\n=== Current plan_type values ===")
        cursor.execute("SELECT id, name, plan_type FROM subscription_plans ORDER BY id")
        current_plans = cursor.fetchall()
        
        if not current_plans:
            print("No subscription plans found in database.")
            conn.close()
            return True
            
        for plan_id, name, plan_type in current_plans:
            print(f"  ID {plan_id}: {name} -> {plan_type!r}")
        
        # Check if we need to make any changes
        needs_fix = any(plan_type in ['subscription', 'one_time'] for _, _, plan_type in current_plans)
        
        if not needs_fix:
            print("\n✓ All plan_type values are already correct!")
            conn.close()
            return True
        
        print("\n=== Applying fixes ===")
        
        # Update subscription -> SUBSCRIPTION
        cursor.execute("UPDATE subscription_plans SET plan_type = 'SUBSCRIPTION' WHERE plan_type = 'subscription'")
        subscription_updated = cursor.rowcount
        if subscription_updated > 0:
            print(f"  Updated {subscription_updated} record(s): 'subscription' -> 'SUBSCRIPTION'")
        
        # Update one_time -> ONE_TIME
        cursor.execute("UPDATE subscription_plans SET plan_type = 'ONE_TIME' WHERE plan_type = 'one_time'")
        one_time_updated = cursor.rowcount
        if one_time_updated > 0:
            print(f"  Updated {one_time_updated} record(s): 'one_time' -> 'ONE_TIME'")
        
        # Commit changes
        conn.commit()
        
        # Verify the changes
        print("\n=== Updated plan_type values ===")
        cursor.execute("SELECT id, name, plan_type FROM subscription_plans ORDER BY id")
        updated_plans = cursor.fetchall()
        
        for plan_id, name, plan_type in updated_plans:
            print(f"  ID {plan_id}: {name} -> {plan_type!r}")
        
        # Check for any unexpected values
        cursor.execute("SELECT DISTINCT plan_type FROM subscription_plans")
        distinct_values = [row[0] for row in cursor.fetchall()]
        
        expected_values = {'SUBSCRIPTION', 'ONE_TIME'}
        unexpected = set(distinct_values) - expected_values
        
        if unexpected:
            print(f"\n⚠️  Warning: Found unexpected plan_type values: {unexpected}")
            print("   These may cause issues with the application.")
        else:
            print(f"\n✓ All plan_type values are now correct: {sorted(distinct_values)}")
        
        conn.close()
        
        total_updated = subscription_updated + one_time_updated
        print(f"\n✅ Successfully updated {total_updated} record(s)")
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def main():
    """Main function."""
    
    # Get database path from command line or use default
    db_path = sys.argv[1] if len(sys.argv) > 1 else "bot.db"
    
    print("=== PlanType Enum Fix Script ===")
    print(f"Target database: {db_path}")
    
    # Ask for confirmation if not in automated mode
    if len(sys.argv) <= 2:  # Interactive mode
        response = input("\nThis will modify the database. Continue? (y/N): ")
        if response.lower() not in ['y', 'yes']:
            print("Operation cancelled.")
            return
    
    # Apply the fix
    success = fix_plan_type_enum(db_path)
    
    if success:
        print("\n🎉 Fix completed successfully!")
        print("You can now restart the application.")
    else:
        print("\n💥 Fix failed. Please check the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()