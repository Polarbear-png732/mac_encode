@echo off
setlocal
chcp 65001 >nul

set "ROOT=%~dp0"

echo ==============================================
echo Python 代码行数统计
echo ==============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$root = (Resolve-Path '%ROOT%').Path; $excludePattern = '\\venv\\|\\.git\\|\\build\\|\\dist\\|\\__pycache__\\|\\.mypy_cache\\|\\.pytest_cache\\'; $files = Get-ChildItem -Path $root -Recurse -File -Filter *.py | Where-Object { $_.FullName -notmatch $excludePattern }; if(-not $files) { Write-Host '未找到 .py 文件。'; exit 0 }; $rows = foreach($f in $files) { $relative = $f.FullName.Substring($root.Length).TrimStart('\\'); $lineCount = 0; try { $lineCount = [System.IO.File]::ReadAllLines($f.FullName).Length } catch { $lineCount = (Get-Content -Path $f.FullName | Measure-Object -Line).Lines }; [PSCustomObject]@{ 文件 = $relative; 行数 = $lineCount } }; $total = ($rows | Measure-Object -Property 行数 -Sum).Sum; Write-Host ('项目路径: ' + $root); Write-Host ('Python 文件数: ' + $rows.Count); Write-Host ('总行数: ' + $total); Write-Host ''; $rows | Sort-Object 行数 -Descending | Format-Table -AutoSize"

echo.
echo 统计完成，按任意键关闭...
pause >nul

endlocal
