@echo off
REM Lance batcheck et ouvre le navigateur.
cd /d "%~dp0"
start "" http://127.0.0.1:8765
python server.py
