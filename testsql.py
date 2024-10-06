import mysql.connector
from mysql.connector import Error
from flask import Flask, jsonify
import os
from dotenv import load_dotenv

load_dotenv()


app = Flask(__name__)

def test_sql_connection():
    result = {}
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
            result['server_info'] = f"Đã kết nối thành công đến MySQL Server phiên bản {db_info}"
            
            cursor = connection.cursor()
            cursor.execute("SELECT DATABASE();")
            record = cursor.fetchone()
            result['database'] = f"Bạn đã kết nối đến database: {record[0]}"
            result['status'] = 'success'

    except Error as e:
        result['error'] = f"Lỗi khi kết nối đến MySQL: {str(e)}"
        result['status'] = 'error'
    
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()
            result['connection_closed'] = "Kết nối MySQL đã đóng"

    return result

@app.route('/')
def index():
    result = test_sql_connection()
    return jsonify(result)

if __name__ == "__main__":
    app.run()