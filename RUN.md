# winget install GnuWin32.Make cài lệnh make

#lệnh dài 
Lệnh để tự chạy lần sau
Cần 2 cửa sổ terminal vì mỗi server chiếm một cửa sổ.

Terminal 1 — Backend:


cd E:\VSCSTD\VIN\P-055
.venv\Scripts\activate
uvicorn src.main:app --reload --port 8000
Terminal 2 — Frontend:


cd E:\VSCSTD\VIN\P-055\frontend
npm run dev
Dừng: Ctrl+C ở mỗi cửa sổ.