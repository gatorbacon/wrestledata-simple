@echo off
cd /d "C:\Users\lives\Documents\CRSR\wrestling-projects\wrestling-new"
set /p msg="Enter commit message: "
git add .
git commit -m "%msg%"
git push origin main
echo Backup completed!
pause