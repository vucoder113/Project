# QR khách hàng

## Cài đặt

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Chạy

```powershell
py app.py
```

Mở http://127.0.0.1:5000 và tải file Excel lên. Mỗi dòng sẽ có một QR và một trang thông tin riêng.

File Excel tải lên sẽ được cập nhật cộng dồn; bản ghi trùng mã khách hàng, email, số điện thoại hoặc họ tên sẽ được cập nhật thay vì tạo lại. Admin có thể tải dữ liệu check-in ở định dạng Excel hoặc CSV.

Trên Render, `render.yaml` đã cấu hình persistent disk cho thư mục `data`. Khi tạo service, cần dùng gói Render có hỗ trợ persistent disk; gói miễn phí không giữ file sau khi deploy hoặc khởi động lại.

QR chung tại trang admin dẫn đến form đăng ký khách mới. Sau khi gửi form, khách được tạo QR và ghi nhận check-in ngay lập tức.

Để điện thoại khác quét được trong cùng Wi-Fi, chạy bằng địa chỉ IP của máy và dùng URL đó làm địa chỉ máy chủ công khai khi cần.
