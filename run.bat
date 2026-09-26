@echo off
chcp 65001 > nul
echo Запуск AutoTranslator...
python main.py
if errorlevel 1 (
    echo.
    echo Ошибка при запуске. Убедитесь, что зависимости установлены:
    echo pip install -r requirements.txt
    pause
)
