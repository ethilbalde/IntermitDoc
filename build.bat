@echo off
cd /d "E:\claude programe\PDF Classifier"

echo Fermeture de IntermitDoc si ouvert...
taskkill /f /im IntermitDoc.exe >nul 2>&1
timeout /t 2 /nobreak >nul

echo Nettoyage de l'ancien build...
if exist "dist\IntermitDoc" (
    rmdir /s /q "dist\IntermitDoc" 2>nul
    if exist "dist\IntermitDoc" (
        echo ERREUR : impossible de supprimer dist\IntermitDoc
        echo Fermez tout programme qui utilise ce dossier puis relancez.
        pause
        exit /b 1
    )
)

echo Verification de PyInstaller...
python -m PyInstaller --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Installation de PyInstaller...
    pip install pyinstaller
)

echo Compilation en cours ^(2-3 minutes^)...
python -m PyInstaller pdf_classifier.spec --noconfirm > build_log.txt 2>&1
echo.
if %ERRORLEVEL% EQU 0 (
    echo BUILD OK -- dist\IntermitDoc\IntermitDoc.exe
) else (
    echo BUILD ECHOUE -- details :
    type build_log.txt | findstr /i "error\|Error\|ERROR\|Traceback\|PermissionError"
)
pause
