import os
from dotenv import load_dotenv
import mysql.connector
from flask_bcrypt import Bcrypt

load_dotenv()  # Load biến môi trường từ .env

bcrypt = Bcrypt()

# Kết nối tới cơ sở dữ liệu
mydb = mysql.connector.connect(
    host=os.getenv('DB_CLOUD_HOST'),
    user=os.getenv('DB_CLOUD_USER'),
    password=os.getenv('DB_CLOUD_PASSWORD'),
    database=os.getenv('DB_CLOUD_NAME'),
)

try:
    mycursor = mydb.cursor(dictionary=True)
    print("Kết nối cơ sở dữ liệu thành công")
except mysql.connector.Error as e:
    print(f"Lỗi kết nối cơ sở dữ liệu: {e}")
    exit(1)

# Lấy tất cả người dùng
mycursor.execute("SELECT id, username, password FROM users")
users = mycursor.fetchall()

for user in users:
    # Kiểm tra xem mật khẩu đã được mã hóa chưa (ví dụ: kiểm tra độ dài hoặc sử dụng regex)
    if not user['password'].startswith('$2b$'):  # Đây là tiền tố của bcrypt
        try:
            # Giả sử mật khẩu hiện tại là plain text, chúng ta sẽ mã hóa nó
            hashed_password = bcrypt.generate_password_hash(
                user['password']).decode('utf-8')

            # Cập nhật mật khẩu đã mã hóa vào cơ sở dữ liệu
            sql = "UPDATE users SET password = %s WHERE id = %s"
            val = (hashed_password, user['id'])
            mycursor.execute(sql, val)
            print(f"Mật khẩu của người dùng ID {user['id']} đã được mã hóa.")
        except Exception as e:
            print(f"Lỗi khi mã hóa mật khẩu cho người dùng ID {
                  user['id']}: {e}")
    else:
        print(f"Mật khẩu của người dùng ID {
              user['id']} đã được mã hóa. Bỏ qua.")

mydb.commit()

print(f"{mycursor.rowcount} record(s) đã được cập nhật.")
