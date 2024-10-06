import os
import sqlalchemy
from flask import Flask, jsonify
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector

load_dotenv()

app = Flask(__name__)

# Lấy thông tin kết nối Cloud SQL từ biến môi trường
instance_connection_name = os.getenv('DB_CLOUD_HOST')
db_user = os.getenv('DB_CLOUD_USER')
db_pass = os.getenv('DB_CLOUD_PASSWORD')
db_name = os.getenv('DB_CLOUD_NAME')

# Tạo chuỗi kết nối Cloud SQL
connection_string = (
    f'mysql+pymysql://{db_user}:{db_pass}@{instance_connection_name}/{db_name}')

# Tạo pool kết nối
pool = sqlalchemy.create_engine(
    connection_string,
    pool_size=5,
    max_overflow=2,
    pool_timeout=30,
    pool_recycle=1800
)

def test_sql_connection():
    result = {}
    try:
        with pool.connect() as conn:
            # Sử dụng sqlalchemy.text để tạo đối tượng SQL Expression
            db_info = conn.execute(sqlalchemy.text('SELECT VERSION()')).fetchone()
            result['server_info'] = f"Đã kết nối thành công đến MySQL Server phiên bản {db_info[0]}"
            
            current_db = conn.execute(sqlalchemy.text('SELECT DATABASE()')).fetchone()
            result['database'] = f"Bạn đã kết nối đến database: {current_db[0]}"
            result['status'] = 'success'

    except Exception as e:
        result['error'] = f"Lỗi khi kết nối đến MySQL: {str(e)}"
        result['status'] = 'error'

    return result

@app.route('/')
def index():
    result = test_sql_connection()
    return jsonify(result)

if __name__ == "__main__":
    app.run()