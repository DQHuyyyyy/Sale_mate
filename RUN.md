### TERMINAL 1:
AI Core: cd PS E:\VSCSTD\VIN\P-055>
python.exe -m uvicorn src.main:app --reload --port 8001

### TERMINAL 2: Backend
PS E:\VSCSTD\VIN\P-055\interface\backend>
python.exe -m uvicorn app.main:app --reload --port 8000

### TERMINAL 3: Frontedc
PS E:\VSCSTD\VIN\P-055\interface\frontend>
npm run dev