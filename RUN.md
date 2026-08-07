# Cài lệnh make trên Windows

```powershell
winget install GnuWin32.Make
```

Cài xong PowerShell **vẫn báo "make is not recognized"** — installer không thêm
vào PATH. Chạy một lần nữa, rồi mở terminal mới:

```powershell
[Environment]::SetEnvironmentVariable('Path',
  [Environment]::GetEnvironmentVariable('Path','User') + ';C:\Program Files (x86)\GnuWin32\bin',
  'User')
```


#lệnh dài 
Lệnh để tự chạy lần sau
Cần 2 cửa sổ terminal vì mỗi server chiếm một cửa sổ.

Terminal 1 — Backend:


cd E:\VSCSTD\VIN\P-055
.venv\Scripts\activate
uvicorn src.main:app --reload --port 8000
Terminal 2 — Frontend:


cd E:\VSCSTD\VIN\P-055\interface\frontend
npm run dev
Dừng: Ctrl+C ở mỗi cửa sổ.