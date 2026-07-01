<#
.SYNOPSIS
    该脚本用于打包 "Seraphine" .

.PARAMETER dest
    输出的目标路径。默认为当前目录。

.PARAMETER dbg
    是否启用调试模式。如果启用，将不会删除 `.\dist` 目录，也不会创建 7z 文件。

.PARAMETER keepDist
    打包 7z 后保留 `.\dist\Seraphine` 目录。CI 中 tufup 需要该目录生成 tar.gz
    增量包 (见 tufup_repo.py add-bundle), 故 build job 传 -keepDist; 旧的全量
    7z 流程不受影响。

.EXAMPLE
    .\make.ps1 -dbg
#>

param(
    [Parameter()]
    [String]$dest = ".",
    [Switch]$dbg,
    [Switch]$keepDist
)

if ($dbg -and (Test-Path .\dist)) {
    rm -r -Force .\dist
}

# --collect-submodules tufup/tuf: tufup.client 在 tufup_updater._make_client 里
# 延迟 import (函数内), PyInstaller 静态分析虽能识别, 但 tuf 库内部有动态导入,
# 显式 collect-submodules 保证增量更新运行时不缺模块 (bsdiff4 等 C 扩展随之打包).
pyinstaller -w -i .\app\resource\images\logo.ico `
    --collect-submodules tufup `
    --collect-submodules tuf `
    main.py
rm -r -fo .\build
rm -r -fo .\main.spec
rni -path .\dist\main -newName Seraphine
rni -path .\dist\Seraphine\main.exe -newName Seraphine.exe
cpi .\app -destination .\dist\Seraphine -recurse
rm -r .\dist\Seraphine\app\common
rm -r .\dist\Seraphine\app\components
rm -r .\dist\Seraphine\app\lol
rm -Path .\dist\Seraphine\app\resource\game* -r
rm -r .\dist\Seraphine\app\resource\i18n\Seraphine.zh_CN.ts
rm -r .\dist\Seraphine\app\resource\bin\fix_lcu_window.c
rm -r .\dist\Seraphine\app\resource\bin\readme.md
rm -r .\dist\Seraphine\app\view

$files = Get-ChildItem -Path ".\dist\Seraphine\*" -Recurse |
    Select-Object -ExpandProperty FullName |
    ForEach-Object { $_.Replace((Resolve-Path ".\dist\Seraphine").Path + "\", "") }

$files | Out-File -FilePath ".\dist\Seraphine\filelist.txt" -Encoding UTF8

if (! $dbg) {
    7z a $dest\Seraphine.7z .\dist\Seraphine\* -r
    if (! $keepDist) {
        rm -r .\dist
    }
}
