import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

load_dotenv()


def test_sql_connection():
    try:
        # Thay đổi các thông số kết nối theo cấu hình của bạn
        connection = mysql.connector.connect(
            host=os.getenv('DB_CLOUD_HOST'),
            database=os.getenv('DB_CLOUD_NAME'),
            user=os.getenv('DB_CLOUD_USER'),
            password=os.getenv('DB_CLOUD_PASSWORD')
        )

        if connection.is_connected():
            db_info = connection.get_server_info()
            print(f"Đã kết nối thành công đến MySQL Server phiên bản {db_info}")
            
            cursor = connection.cursor()
            cursor.execute("SELECT DATABASE();")
            record = cursor.fetchone()
            print(f"Bạn đã kết nối đến database: {record[0]}")

    except Error as e:
        print(f"Lỗi khi kết nối đến MySQL: {e}")
    
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
            print("Kết nối MySQL đã đóng")

if __name__ == "__main__":
    test_sql_connection()