#!/usr/bin/env python3
"""
Script to drop and recreate specific database objects while preserving Publication and Document data.

This script will:
1. Drop tables that depend on Node/ContentData (Relation, Embedding)
2. Drop Node and ContentData tables
3. Drop and recreate all enums
4. Recreate Node and ContentData tables with updated schema
5. Recreate dependent tables (Relation, Embedding)

Publication and Document tables will be preserved with their data intact.
"""

import sys
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from db.db import engine, get_database_url
from db.schema import SQLModel

def execute_sql_commands(commands):
    """Execute a list of SQL commands with proper transaction handling."""
    with engine.begin() as conn:  # Use begin() for automatic transaction management
        for command in commands:
            print(f"Executing: {command}")
            try:
                conn.execute(text(command))
                print("✓ Success")
            except SQLAlchemyError as e:
                print(f"✗ Error: {e}")
                raise

def drop_dependent_tables():
    """Drop tables that depend on Node/ContentData tables."""
    print("\n1️⃣  Dropping dependent tables...")
    commands = [
        "DROP TABLE IF EXISTS embedding CASCADE;",
        "DROP TABLE IF EXISTS relation CASCADE;",
    ]
    execute_sql_commands(commands)

def drop_main_tables():
    """Drop Node and ContentData tables."""
    print("\n2️⃣  Dropping Node and ContentData tables...")
    commands = [
        "DROP TABLE IF EXISTS contentdata CASCADE;",
        "DROP TABLE IF EXISTS node CASCADE;",
    ]
    execute_sql_commands(commands)

def drop_enums():
    """Drop only enum types used by tables being recreated."""
    print("\n3️⃣  Dropping enums used by Node/ContentData/Relation/Embedding tables...")
    commands = [
        # DocumentType is NOT dropped - it's used by Document table which is preserved
        "DROP TYPE IF EXISTS nodetype CASCADE;",
        "DROP TYPE IF EXISTS tagname CASCADE;",
        "DROP TYPE IF EXISTS sectiontype CASCADE;",
        "DROP TYPE IF EXISTS embeddingsource CASCADE;",
        "DROP TYPE IF EXISTS relationtype CASCADE;",
    ]
    execute_sql_commands(commands)

def recreate_tables():
    """Recreate all tables using SQLModel metadata."""
    print("\n4️⃣  Recreating tables with updated schema...")
    try:
        # This will create all tables, but Publication and Document already exist
        # SQLModel will only create the missing ones
        SQLModel.metadata.create_all(engine)
        print("✓ Tables recreated successfully")
    except SQLAlchemyError as e:
        print(f"✗ Error recreating tables: {e}")
        raise

def print_summary():
    """Print migration summary."""
    print("\n✅ Schema update completed successfully!")
    print("📊 Summary:")
    print("   ✓ Node-related enums: Dropped and recreated")
    print("   ✓ DocumentType enum: Preserved (used by Document table)")
    print("   ✓ Node table: Dropped and recreated")
    print("   ✓ ContentData table: Dropped and recreated") 
    print("   ✓ Relation table: Dropped and recreated")
    print("   ✓ Embedding table: Dropped and recreated")
    print("   ✓ Publication table: Preserved")
    print("   ✓ Document table: Preserved (including type column)")

def main():
    """Main function to drop and recreate schema components."""
    
    print("🗄️  Starting database schema update...")
    print("📋 This will drop and recreate: Node-related enums, Node, ContentData, Relation, Embedding tables")
    print("💾 Publication and Document tables (and DocumentType enum) will be preserved")
    
    # Validate database connection
    try:
        database_url = get_database_url()
        print(f"📡 Connected to database at: {database_url.split('@')[1] if '@' in database_url else 'localhost'}")
    except Exception as e:
        print(f"❌ Failed to get database URL: {e}")
        sys.exit(1)
    
    # Get confirmation
    response = input("\nDo you want to continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Aborted.")
        return
    
    print("\n🔄 Starting schema update process...")
    
    try:
        # Execute migration steps
        drop_dependent_tables()
        drop_main_tables() 
        drop_enums()
        recreate_tables()
        
        print_summary()
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("💡 The database may be in an inconsistent state. Consider running the migration again.")
        sys.exit(1)

if __name__ == "__main__":
    main()