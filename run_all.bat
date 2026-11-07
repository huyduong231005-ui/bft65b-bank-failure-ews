@echo off
REM ==========================================================================
REM  Double-click to run the whole pipeline on Windows (no typing needed).
REM  1. creates the Python environment (.venv) and installs requirements once
REM  2. uses JDK 17 from the "jdk17" folder next to this file (or JAVA_HOME)
REM  3. runs Parts 1, 2, 4, 5, then the Spark steps (Part 3, MLlib), then Excel
REM  The raw data in data_raw\ is used as is: download.py is NOT run, so the
REM  results match the hand-over document exactly.
REM ==========================================================================
setlocal
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"

echo.
echo ==== BFT65B pipeline ====
echo Thu muc: %CD%
echo.

if not exist "data_raw\fdic\manifest_financials.json" (
    echo [LOI] Khong thay du lieu tho data_raw\fdic.
    echo       Hay giai nen day du file zip, hoac chay: %PY% src\download.py ^(mat ~1 gio^)
    goto :fail
)

if exist "%PY%" goto :have_venv
echo [1/3] Tao moi truong Python ^(chi lam lan dau^)...
py -3.11 -m venv .venv 2>nul || python -m venv .venv
if not exist "%PY%" (
    echo [LOI] Khong tim thay Python. Cai Python 3.11 theo huong dan trong BAN_GIAO.docx,
    echo       nho tick "Add python.exe to PATH", roi bam dup lai file nay.
    goto :fail
)
echo [2/3] Cai thu vien ^(mat vai phut, can Internet^)...
"%PY%" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo [LOI] Cai thu vien that bai. Kiem tra ket noi Internet roi bam dup lai.
    rmdir /s /q .venv
    goto :fail
)
:have_venv

REM JDK 17 for Spark: prefer the "jdk17" folder inside the project
if exist "%~dp0jdk17\bin\java.exe" set "JAVA_HOME=%~dp0jdk17"

echo [3/3] Chay pipeline...
for %%s in (p1_storage p2_quality p4_features p5_model) do (
    echo.
    echo ---- %%s ----
    "%PY%" src\%%s.py
    if errorlevel 1 (
        echo [LOI] Buoc %%s bi loi. Chup man hinh nay gui nguoi ho tro.
        goto :fail
    )
)

if not defined JAVA_HOME goto :no_java
if not exist "%JAVA_HOME%\bin\java.exe" goto :no_java
for %%s in (p3_processing p5_mllib) do (
    echo.
    echo ---- %%s ^(Spark, co the mat 10-20 phut^) ----
    "%PY%" src\%%s.py
    if errorlevel 1 (
        echo [LOI] Buoc %%s bi loi. Kiem tra thu muc jdk17 ^(phai co jdk17\bin\java.exe^).
        goto :fail
    )
)
goto :excel

:no_java
echo.
echo [BO QUA] Cac buoc Spark ^(p3_processing, p5_mllib^): chua co JDK 17.
echo          Dat thu muc JDK 17 vao day voi ten "jdk17" ^(phai co jdk17\bin\java.exe^) roi chay lai.

:excel
"%PY%" src\export_excel.py
echo.
echo ==== XONG. Ket qua nam trong thu muc outputs\ ^(xem outputs\results.xlsx^) ====
pause
exit /b 0

:fail
echo.
echo ==== DUNG LAI DO LOI ====
pause
exit /b 1
