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

File Excel tải lên sẽ được cập nhật cộng dồn; bản ghi trùng mã khách hàng, email, số điện thoại hoặc họ tên sẽ được cập nhật thay vì tạo lại. Nếu dòng khách có Email, hệ thống gửi QR sau lần upload đầu tiên; các lần upload lại cùng email sẽ không gửi lại, còn email được đổi sang địa chỉ mới sẽ được gửi lại QR. Admin có thể tải dữ liệu check-in ở định dạng Excel hoặc CSV.

Trên Render, `render.yaml` đã cấu hình persistent disk cho thư mục `data`. Khi tạo service, cần dùng gói Render có hỗ trợ persistent disk; gói miễn phí không giữ file sau khi deploy hoặc khởi động lại.

## Check-in QR

Chỉ admin mở camera trên trang quản lý và quét QR của khách để ghi nhận tham dự. Không yêu cầu GPS, quyền vị trí hoặc cấu hình tọa độ sự kiện. Camera trình duyệt cần chạy trên `https://` hoặc `localhost` và được cấp quyền truy cập camera.

QR dạng URL và QR offline đều chứa mã nội bộ của khách. QR offline đã tạo trước cập nhật này cần được upload lại để bổ sung mã nội bộ.

Khi đăng ký khách mới, Email là trường không bắt buộc. Nếu khách nhập Email, hệ thống sẽ gửi QR đến email đó.

Để điện thoại khác quét được trong cùng Wi-Fi, chạy bằng địa chỉ IP của máy và dùng URL đó làm địa chỉ máy chủ công khai khi cần.
