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

Để điện thoại khác quét được trong cùng Wi-Fi, chạy bằng địa chỉ IP của máy và dùng URL đó làm địa chỉ máy chủ công khai khi cần.
