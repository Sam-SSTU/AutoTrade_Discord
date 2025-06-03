import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv
from sqlalchemy import create_engine
from app.models.base import Base

def reset_database():
    # Load environment variables
    load_dotenv()
    
    # Database connection parameters from environment variables
    dbname = os.getenv("POSTGRES_DB", "autotrade")
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")

    # Connect to PostgreSQL server (to postgres database)
    conn = psycopg2.connect(
        dbname="postgres",
        user=user,
        password=password,
        host=host,
        port=port
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()

    try:
        # Drop existing connections to the database
        cur.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{dbname}'
            AND pid <> pg_backend_pid();
        """)

        # Drop database if exists
        cur.execute(f"DROP DATABASE IF EXISTS {dbname}")
        print(f"Dropped database '{dbname}' if it existed")

        # Create new database
        cur.execute(f"CREATE DATABASE {dbname}")
        print(f"Created new database '{dbname}'")

        # Close connection to postgres database
        cur.close()
        conn.close()

        # Create SQLAlchemy engine
        engine = create_engine(f"postgresql://{user}:{password}@{host}:{port}/{dbname}")

        # Create enum types first
        conn = engine.raw_connection()
        cur = conn.cursor()
        cur.execute("""
            DO $$ BEGIN
                CREATE TYPE platform AS ENUM ('discord');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)
        
        cur.execute("""
            DO $$ BEGIN
                CREATE TYPE kol_category AS ENUM ('crypto', 'stocks', 'futures', 'forex', 'others');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)
        
        # 确保KOLCategory枚举也存在（用于频道表）
        cur.execute("""
            DO $$ BEGIN
                CREATE TYPE kolcategory AS ENUM ('CRYPTO', 'STOCKS', 'FUTURES', 'FOREX', 'OTHERS');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)
        
        conn.commit()
        cur.close()
        conn.close()

        # 导入AI模型确保它们被注册到Base.metadata中
        try:
            from app.ai.models import AIMessage, AIProcessingLog
            print("AI models imported successfully")
        except ImportError as e:
            print(f"Warning: Could not import AI models: {e}")

        # Create all tables (包括AI表)
        Base.metadata.create_all(engine)
        print("Database tables created!")
        
        # 验证AI表是否创建成功
        from sqlalchemy import text
        with engine.connect() as conn:
            # 检查所有表
            result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"))
            all_tables = [row[0] for row in result]
            print(f"All tables created: {all_tables}")
            
            # 检查AI表
            ai_tables = [t for t in all_tables if 'ai_' in t]
            if ai_tables:
                print(f"AI tables found: {ai_tables}")
                
                for table in ai_tables:
                    result = conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position"))
                    columns = [row[0] for row in result]
                    print(f"Table '{table}' columns: {columns}")
            else:
                print("No AI tables found")

    except Exception as e:
        print(f"Error occurred: {str(e)}")
        raise
    finally:
        if 'cur' in locals() and cur is not None:
            cur.close()
        if 'conn' in locals() and conn is not None:
            conn.close()
        print("Database reset completed!")

if __name__ == "__main__":
    reset_database() 